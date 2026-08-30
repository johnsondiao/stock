"""后台数据更新服务 - 开盘时保持数据新鲜

职责划分（架构约定）:
- 本服务（后台常驻）: 开盘时段自动刷新数据
    1. 每5分钟刷新全市场行情快照（新浪批量接口，仅约11个请求）
    2. 用快照价格修补缓存中"正在形成"的5分钟/小时K线（零额外请求）
    3. 滚动增量校正: 按限流速度逐批用K线API校正缓存（兜底精度）
- 选股（前台按需）: 只读缓存，不再边跑边拉API

交易时段: 工作日 9:30-11:30 / 13:00-15:00（未处理节假日）
"""

import time
import threading
from datetime import datetime, timedelta

import pandas as pd

from app.database import get_db
from app.data.provider import get_provider
from app.log_config import get_logger

logger = get_logger("data_updater")

# 每5分钟周期内, 滚动校正处理的股票数量（2请求/只, 约240请求/周期, 限流安全）
ROLL_CHUNK_SIZE = 120


# ── 交易日历 ──────────────────────────────────────────────

def is_trading_time(now: datetime | None = None) -> bool:
    """是否处于交易时段（含前后5分钟缓冲, 保证收盘K线能刷新到）"""
    now = now or datetime.now()
    if now.weekday() >= 5:  # 周六日
        return False
    t = now.time()
    from datetime import time as dtime
    morning = dtime(9, 25) <= t <= dtime(11, 35)
    afternoon = dtime(12, 55) <= t <= dtime(15, 5)
    return morning or afternoon


def _next_wakeup(now: datetime) -> float:
    """距离下次该醒来的秒数: 交易时段内对齐5分钟边界, 否则60秒后再检查"""
    if is_trading_time(now):
        sec = now.minute * 60 + now.second
        return max(300 - sec % 300, 5)
    return 60.0


def current_5min_slot(now: datetime) -> datetime | None:
    """当前正在形成的5分钟K线的时间戳（结束时间标注）"""
    t = now.time()
    from datetime import time as dtime
    if dtime(9, 30) < t <= dtime(11, 30):
        base = now.replace(hour=9, minute=30, second=0, microsecond=0)
        elapsed = (now - base).total_seconds()
    elif dtime(13, 0) < t <= dtime(15, 0):
        base = now.replace(hour=13, minute=0, second=0, microsecond=0)
        elapsed = (now - base).total_seconds()
    else:
        return None
    n = max(1, int((elapsed + 299) // 300))  # 向上取整到5分钟
    return base + timedelta(seconds=n * 300)


def current_hourly_slot(now: datetime) -> datetime | None:
    """当前正在形成的小时K线时间戳（结束时间标注: 10:30/11:30/14:00/15:00）"""
    t = now.time()
    from datetime import time as dtime
    if dtime(9, 30) < t <= dtime(10, 30):
        return now.replace(hour=10, minute=30, second=0, microsecond=0)
    if dtime(10, 30) < t <= dtime(11, 30):
        return now.replace(hour=11, minute=30, second=0, microsecond=0)
    if dtime(13, 0) < t <= dtime(14, 0):
        return now.replace(hour=14, minute=0, second=0, microsecond=0)
    if dtime(14, 0) < t <= dtime(15, 0):
        return now.replace(hour=15, minute=0, second=0, microsecond=0)
    return None


# ── 快照修补正在形成的K线 ────────────────────────────────

def _patch_table(table: str, code: str, slot: datetime,
                 price: float, day_volume: float):
    """用快照最新价修补指定表的当前形成中K线"""
    slot_str = slot.strftime("%Y-%m-%d %H:%M:%S")
    day_str = slot.strftime("%Y-%m-%d")

    with get_db() as conn:
        last = conn.execute(
            f"SELECT date, high, low FROM {table} WHERE code=? ORDER BY date DESC LIMIT 1",
            (code,),
        ).fetchone()

        # 当日已完结K线的成交量之和 → 估算当前根成交量
        vol_row = conn.execute(
            f"SELECT COALESCE(SUM(volume),0) FROM {table} "
            f"WHERE code=? AND date>=? AND date<?",
            (code, day_str, slot_str),
        ).fetchone()
        est_vol = max(0.0, day_volume - vol_row[0]) if day_volume > 0 else 0.0

        if last is None or last["date"] < slot_str:
            # 新的一天或新K线: 插入
            conn.execute(
                f"INSERT OR REPLACE INTO {table} (code, date, open, high, low, close, volume) "
                f"VALUES (?,?,?,?,?,?,?)",
                (code, slot_str, price, price, price, price, est_vol),
            )
        elif last["date"] == slot_str:
            # 正在形成的K线: 更新
            new_high = max(last["high"], price)
            new_low = min(last["low"], price)
            conn.execute(
                f"UPDATE {table} SET high=?, low=?, close=?, volume=? "
                f"WHERE code=? AND date=?",
                (new_high, new_low, price, est_vol, code, slot_str),
            )
        # last.date > slot: 缓存数据更新, 跳过


def patch_forming_candles(snapshot: pd.DataFrame, now: datetime) -> int:
    """用行情快照修补全部缓存股票的当前形成中K线, 返回修补股票数"""
    slot5 = current_5min_slot(now)
    slot_h = current_hourly_slot(now)
    if slot5 is None and slot_h is None:
        return 0

    patched = 0
    for _, row in snapshot.iterrows():
        code = row["code"]
        price = float(row.get("price", 0))
        if price <= 0:
            continue
        day_volume = float(row.get("volume", 0))
        if slot5 is not None:
            _patch_table("kline_5min", code, slot5, price, day_volume)
        if slot_h is not None:
            _patch_table("hourly_kline", code, slot_h, price, day_volume)
        patched += 1
    return patched


# ── 滚动增量校正 ──────────────────────────────────────────

_roll_codes: list[str] = []
_roll_pos: int = 0


def _roll_refresh(provider):
    """每次周期取一批股票, 用K线API做增量校正（精度兜底）"""
    global _roll_codes, _roll_pos

    if not _roll_codes:
        from app.data import cache
        _roll_codes = sorted(cache.get_cached_codes("hourly_kline"))
        _roll_pos = 0
        logger.info("滚动校正: 待维护股票 %d 只", len(_roll_codes))
    if not _roll_codes:
        return

    chunk = _roll_codes[_roll_pos:_roll_pos + ROLL_CHUNK_SIZE]
    _roll_pos = (_roll_pos + ROLL_CHUNK_SIZE) % len(_roll_codes)

    ok, err = 0, 0
    for code in chunk:
        try:
            provider.get_hourly_kline(code)
            provider.get_5min_kline(code)
            ok += 1
        except Exception as e:
            err += 1
            logger.debug("滚动校正失败 %s: %s", code, e)
    logger.info("滚动校正: 本批 %d 只 (OK:%d ERR:%d), 下次从 #%d 开始",
                len(chunk), ok, err, _roll_pos)


# ── 常驻线程 ──────────────────────────────────────────────

_stop_event = threading.Event()
_thread: threading.Thread | None = None


def _loop():
    provider = get_provider()
    logged_idle_day = None

    while not _stop_event.is_set():
        now = datetime.now()

        if not is_trading_time(now):
            if logged_idle_day != now.date():
                logger.info("当前非交易时段, 数据更新服务待命")
                logged_idle_day = now.date()
            _stop_event.wait(_next_wakeup(now))
            continue

        try:
            # 1. 刷新全市场行情快照
            snapshot = provider.get_all_stocks(force_refresh=True)
            if not snapshot.empty:
                # 2. 用快照修补正在形成的K线（零请求）
                n = patch_forming_candles(snapshot, datetime.now())
                logger.info("快照已刷新: %d 只, 修补形成中K线 %d 只", len(snapshot), n)
                # 3. 滚动增量校正一批（限流内）
                _roll_refresh(provider)
        except Exception as e:
            logger.warning("数据更新周期异常: %s", e)

        _stop_event.wait(_next_wakeup(datetime.now()))


def start():
    """启动后台数据更新线程"""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_loop, name="data-updater", daemon=True)
    _thread.start()
    logger.info("后台数据更新服务已启动（开盘时段每5分钟刷新）")


def stop():
    """停止后台数据更新线程"""
    _stop_event.set()
    if _thread is not None:
        _thread.join(timeout=5)
    logger.info("后台数据更新服务已停止")

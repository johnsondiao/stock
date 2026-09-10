"""
日线一致性保障模块

职责:
  检测 daily_kline 是否落后于最新交易日, 落后则用新浪 scale=240 接口
  以受控并发的方式批量补齐。

设计取舍:
  - 盘中由 data_updater._patch_daily 用行情快照零请求维护当日日线,
    本模块只负责"服务长时间未运行"造成的整段缺口(跨周末/假期/宕机)。
  - 因此这里不走全局 RateLimiter(30/分钟, 补 3300 只要 110 分钟),
    而是用独立并发池(实测约 10 只/秒, 全市场约 5 分钟), 只在自检时触发,
    且可通过 ensure_daily_fresh(concurrency=N) 收敛。
"""

import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from app.database import get_db
from app.log_config import get_logger

logger = get_logger(__name__)

URL = ("https://vip.stock.finance.sina.com.cn/quotes_service/api/"
       "json_v2.php/CN_MarketData.getKLineData")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://finance.sina.com.cn",
}
BACKFILL_DAYS = 30          # 每只拉取的交易日根数(覆盖一个半月的缺口)


def sina_symbol(code: str) -> str:
    return f"sh{code}" if code.startswith(("6", "9")) else f"sz{code}"


def norm_date(day: str) -> str:
    """新浪返回 'YYYY-MM-DD', 统一为与 cache 一致的 'YYYY-MM-DD 00:00:00'"""
    return f"{day[:10]} 00:00:00"


def latest_daily_date() -> str | None:
    """daily_kline 中最新的交易日 'YYYY-MM-DD', 表空则返回 None"""
    with get_db() as conn:
        row = conn.execute("SELECT MAX(date) FROM daily_kline").fetchone()
    return row[0][:10] if row and row[0] else None


def day_coverage(day: str) -> int:
    """daily_kline 中某交易日(YYYY-MM-DD)的覆盖只数"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM daily_kline WHERE substr(date,1,10)=?",
            (day[:10],)).fetchone()
    return row[0] if row else 0


MIN_COVERAGE = 2000        # 低于此数视为该交易日不完整(全市场约3200只)


def recent_incomplete_days(min_coverage: int = MIN_COVERAGE,
                           lookback: int = 15) -> list[str]:
    """
    找出昨天及之前、daily_kline 覆盖不足的交易日。

    以 hourly_kline 的日期集合为"交易日参考"(它由滚动刷新维护,
    实践中始终完整)。排除今天: 当日日线由盘中 patch_daily 渐进写入,
    收盘前覆盖少是正常的, 不能据此触发补齐。

    背景: 仅比较最新日期不够 —— 盘中 patch_daily 曾只写入 2 只股票,
    使 latest 日期前进但数据是空的, 导致连续多日静默缺口。
    """
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT substr(date,1,10) FROM hourly_kline "
            "WHERE date >= date('now', ?) ORDER BY 1",
            (f"-{lookback} days",)).fetchall()
    today = time.strftime("%Y-%m-%d")
    return [d for (d,) in rows
            if d < today and day_coverage(d) < min_coverage]


def cached_codes() -> list[str]:
    with get_db() as conn:
        return [r[0] for r in conn.execute(
            "SELECT DISTINCT code FROM daily_kline ORDER BY code")]


def _fetch_one(code: str, retries: int = 2) -> tuple[str, list[tuple] | None]:
    for attempt in range(retries + 1):
        try:
            r = requests.get(URL, params={
                "symbol": sina_symbol(code), "scale": "240",
                "ma": "no", "datalen": BACKFILL_DAYS,
            }, headers=HEADERS, timeout=12)
            r.raise_for_status()
            items = r.json()
            if not items:
                return code, []
            rows = []
            for it in items:
                try:
                    rows.append((
                        code, norm_date(it["day"]),
                        float(it["open"]), float(it["high"]),
                        float(it["low"]), float(it["close"]),
                        float(it["volume"]),
                    ))
                except (KeyError, ValueError, TypeError):
                    continue
            return code, rows
        except Exception as e:
            if attempt == retries:
                logger.debug("日线补齐失败 %s: %s", code, e)
                return code, None
            time.sleep(1.0 * (attempt + 1))
    return code, None


def _write(rows_by_code: dict[str, list[tuple]]) -> int:
    """upsert 写回, 只更新 OHLCV, 保留原 amount 字段, 返回写入行数"""
    total = 0
    with get_db() as conn:
        for code, rows in rows_by_code.items():
            if not rows:
                continue
            conn.executemany(
                "INSERT INTO daily_kline "
                "(code, date, open, high, low, close, volume, amount) "
                "VALUES (?,?,?,?,?,?,?,0) "
                "ON CONFLICT(code, date) DO UPDATE SET "
                "open=excluded.open, high=excluded.high, low=excluded.low, "
                "close=excluded.close, volume=excluded.volume",
                rows,
            )
            total += len(rows)
    return total


def backfill(codes: list[str], concurrency: int = 8,
             progress_every: int = 1000) -> dict:
    """
    批量补齐指定股票的日线
    :return: {ok, failed, rows, seconds}
    """
    if not codes:
        return {"ok": 0, "failed": 0, "rows": 0, "seconds": 0.0}

    t0 = time.time()
    collected: dict[str, list[tuple]] = {}
    failed: list[str] = []

    logger.info("日线补齐: 开始 %d 只, 并发 %d", len(codes), concurrency)
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        for n, (code, rows) in enumerate(
                ex.map(lambda c: _fetch_one(c), codes), 1):
            if rows is None:
                failed.append(code)
            else:
                collected[code] = rows
            if n % progress_every == 0 or n == len(codes):
                logger.info("日线补齐进度 %d/%d (失败 %d)",
                            n, len(codes), len(failed))

    # 失败项串行重试一次, 避免零星网络抖动留下空洞
    if failed:
        logger.info("日线补齐: 串行重试 %d 只", len(failed))
        retry_ok = []
        for code in failed:
            _, rows = _fetch_one(code, retries=3)
            if rows is not None:
                collected[code] = rows
                retry_ok.append(code)
            time.sleep(0.2)
        failed = [c for c in failed if c not in retry_ok]

    rows = _write(collected)
    el = time.time() - t0
    logger.info("日线补齐完成: 成功 %d / 失败 %d / %d 行 / %.0f秒",
                len(collected), len(failed), rows, el)
    return {"ok": len(collected), "failed": len(failed),
            "rows": rows, "seconds": el}


_backfill_lock = threading.Lock()


def ensure_daily_fresh(target_date: str | None = None,
                       concurrency: int = 8,
                       force: bool = False) -> bool:
    """
    确保日线已覆盖到 target_date(默认今天)。已覆盖则直接返回, 不做任何请求。
    :return: 是否执行了补齐
    """
    if not _backfill_lock.acquire(blocking=False):
        return False          # 已有补齐任务在跑, 避免重复触发
    try:
        target = target_date or time.strftime("%Y-%m-%d")
        latest = latest_daily_date()
        gaps = recent_incomplete_days()
        if not force and latest and latest >= target and not gaps:
            logger.debug("日线已是最新 (%s >= %s, 近期无缺口), 跳过补齐",
                         latest, target)
            return False

        if gaps:
            logger.warning("日线存在覆盖缺口 %s (库中最新 %s, 目标 %s)"
                           " → 触发补齐", gaps, latest, target)
        else:
            logger.warning("日线落后: 库中最新 %s, 目标 %s → 触发补齐",
                           latest, target)
        codes = cached_codes()
        if not codes:
            logger.error("daily_kline 为空, 无法补齐(请先运行 download_data.py)")
            return False
        stat = backfill(codes, concurrency=concurrency)
        logger.info("日线补齐结果: %s", stat)
        return True
    finally:
        _backfill_lock.release()

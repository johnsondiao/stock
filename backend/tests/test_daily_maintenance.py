"""日线维护回归测试

背景:
  后台更新服务曾只维护 hourly_kline / kline_5min, 遗漏 daily_kline,
  导致日线缓存长期冻结在 8/28, 选股器的"日线趋势确认"关卡一直吃陈旧数据。
  本测试锁定修复后的行为, 防止回归。

覆盖:
  - patch_daily 用行情快照的 OHLC 写入当日日线
  - 同日重复调用为更新而非插入(不产生重复行)
  - 跳过无效价格、OHLC 缺失时兜底
"""

from datetime import datetime

import pandas as pd
import pytest

from app.config import settings
from app.database import init_db, close_db, get_db
from app.log_config import setup_logging


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """把数据库指向临时文件, 避免污染真实缓存"""
    monkeypatch.setattr(settings, "db_path", tmp_path / "stock.db")
    close_db()                 # 丢弃线程内缓存的旧连接
    setup_logging()
    init_db()
    yield
    close_db()


def _seed(code: str = "600218"):
    with get_db() as conn:
        conn.executemany(
            "INSERT INTO daily_kline "
            "(code, date, open, high, low, close, volume, amount) "
            "VALUES (?,?,?,?,?,?,?,0)",
            [
                (code, "2026-08-28 00:00:00", 7.0, 7.2, 6.9, 7.10, 1000),
                (code, "2026-08-31 00:00:00", 7.1, 7.4, 7.0, 7.30, 1200),
            ],
        )


def _snap(**over) -> pd.DataFrame:
    row = {"code": "600218", "price": 7.55, "open": 7.32,
           "high": 7.60, "low": 7.28, "volume": 8888.0}
    row.update(over)
    return pd.DataFrame([row])


def _last(code: str = "600218"):
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 1",
            (code,),
        ).fetchone()


def _count(code: str = "600218") -> int:
    with get_db() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM daily_kline WHERE code=?", (code,)
        ).fetchone()[0]


def test_current_daily_slot_normalizes_to_midnight():
    from app.service.data_updater import current_daily_slot
    slot = current_daily_slot(datetime(2026, 9, 7, 14, 37, 12))
    assert slot.strftime("%Y-%m-%d %H:%M:%S") == "2026-09-07 00:00:00"


def test_patch_daily_inserts_new_bar():
    """新交易日首次调用: 插入一根完整日线"""
    from app.service.data_updater import patch_daily, current_daily_slot

    _seed()
    n = patch_daily(_snap(), current_daily_slot(datetime(2026, 9, 1, 10, 15)))

    assert n == 1
    row = _last()
    assert row["date"] == "2026-09-01 00:00:00"
    assert row["open"] == 7.32
    assert row["high"] == 7.60
    assert row["low"] == 7.28
    assert row["close"] == 7.55
    assert row["volume"] == 8888.0


def test_patch_daily_updates_in_place_without_duplicates():
    """同一交易日反复调用(每5分钟一次): 更新而非堆积重复行"""
    from app.service.data_updater import patch_daily, current_daily_slot

    _seed()
    slot = current_daily_slot(datetime(2026, 9, 1, 10, 15))
    patch_daily(_snap(price=7.40, high=7.45, low=7.20, volume=1000), slot)
    patch_daily(_snap(price=7.62, high=7.70, low=7.22, volume=2500), slot)

    assert _count() == 3                    # 2 根历史 + 1 根当日, 无重复
    row = _last()
    assert row["close"] == 7.62
    assert row["high"] == 7.70              # 取最新快照, 不累积最高价
    assert row["volume"] == 2500


def test_patch_daily_skips_invalid_price():
    """停牌/无效行情(price<=0)不写入"""
    from app.service.data_updater import patch_daily, current_daily_slot

    _seed()
    n = patch_daily(_snap(price=0), current_daily_slot(datetime(2026, 9, 1, 10, 15)))

    assert n == 0
    assert _count() == 2
    assert _last()["date"] == "2026-08-31 00:00:00"


def test_patch_daily_falls_back_when_ohlc_missing():
    """集合竞价阶段 OHLC 缺失时, 用最新价兜底, 不得写入 0 值"""
    from app.service.data_updater import patch_daily, current_daily_slot

    _seed()
    patch_daily(_snap(open=0, high=0, low=0, price=7.50),
                current_daily_slot(datetime(2026, 9, 1, 9, 26)))

    row = _last()
    assert row["open"] == 7.50
    assert row["high"] == 7.50
    assert row["low"] == 7.50
    assert row["close"] == 7.50


def test_patch_daily_handles_multiple_codes():
    """批量写入覆盖全部代码"""
    from app.service.data_updater import patch_daily, current_daily_slot

    _seed("600218")
    _seed("000089")
    snap = pd.DataFrame([
        {"code": "600218", "price": 7.55, "open": 7.32,
         "high": 7.60, "low": 7.28, "volume": 8888.0},
        {"code": "000089", "price": 6.64, "open": 6.57,
         "high": 6.65, "low": 6.56, "volume": 4321.0},
    ])

    n = patch_daily(snap, current_daily_slot(datetime(2026, 9, 1, 14, 45)))

    assert n == 2
    assert _last("600218")["close"] == 7.55
    assert _last("000089")["close"] == 6.64


def test_daily_backfill_ensure_is_noop_when_fresh(monkeypatch):
    """日线已是最新时, ensure_daily_fresh 不触发任何网络请求"""
    import app.data.daily_backfill as bf

    _seed("600218")
    called = []
    monkeypatch.setattr(bf, "backfill", lambda *a, **k: called.append(1))

    ran = bf.ensure_daily_fresh(target_date="2026-08-31")

    assert ran is False
    assert called == []


def test_daily_backfill_detects_gap(monkeypatch):
    """日线落后于目标日时触发补齐"""
    import app.data.daily_backfill as bf

    _seed("600218")                      # 最新 8/31
    captured = {}
    monkeypatch.setattr(
        bf, "backfill",
        lambda codes, **kw: captured.setdefault("codes", codes) or
        {"ok": 0, "failed": 0, "rows": 0, "seconds": 0.0})

    ran = bf.ensure_daily_fresh(target_date="2026-09-04")

    assert ran is True
    assert captured["codes"] == ["600218"]


def test_recent_incomplete_days_uses_hourly_calendar(monkeypatch):
    """hourly 有某交易日但 daily 覆盖不足 → 检出缺口(9/7 事故回归)"""
    from datetime import datetime, timedelta
    import app.data.daily_backfill as bf

    day3 = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    with get_db() as conn:
        # 当日 hourly 完整(以 3 天前为"历史交易日")
        conn.execute(
            "INSERT INTO hourly_kline (code, date, open, high, low, close, "
            "volume) VALUES ('600218', ?, 7, 7.2, 6.9, 7.1, 100)",
            (f"{day3} 10:30:00",))
        # daily 只有 1 只 → 覆盖不足
        conn.execute(
            "INSERT INTO daily_kline (code, date, open, high, low, close, "
            "volume, amount) VALUES ('600218', ?, 7, 7.2, 6.9, 7.1, 100, 0)",
            (f"{day3} 00:00:00",))

    gaps = bf.recent_incomplete_days(min_coverage=2)

    assert gaps == [day3]


def test_ensure_fresh_triggers_on_sparse_coverage(monkeypatch):
    """最新日期已达目标、但存在覆盖缺口时, 仍必须触发补齐(核心回归)"""
    import app.data.daily_backfill as bf

    _seed("600218")                      # latest=8/31
    called = []
    monkeypatch.setattr(bf, "recent_incomplete_days", lambda **kw: ["2026-09-07"])
    monkeypatch.setattr(bf, "backfill",
                        lambda *a, **k: called.append(1) or
                        {"ok": 0, "failed": 0, "rows": 0, "seconds": 0.0})

    ran = bf.ensure_daily_fresh(target_date="2026-08-31")   # latest >= target

    assert ran is True
    assert called == [1]


def test_ensure_fresh_ignores_today_sparse_coverage(monkeypatch):
    """今天的覆盖少是盘中正常现象, 不得据此触发补齐"""
    import app.data.daily_backfill as bf

    _seed("600218")
    called = []
    monkeypatch.setattr(bf, "backfill", lambda *a, **k: called.append(1))

    ran = bf.ensure_daily_fresh(target_date="2026-08-31")

    assert ran is False
    assert called == []

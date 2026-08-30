"""测试 SQLite 缓存层"""

import pytest
import pandas as pd
import numpy as np
from app.log_config import setup_logging
from app.database import init_db, get_db
from app.data.cache import (
    save_kline, load_kline, get_latest_cached_date,
    get_cached_codes, get_cache_stats,
    save_snapshot, load_snapshot, is_snapshot_fresh,
    save_screen_task, load_screen_task, list_screen_tasks,
)


@pytest.fixture(autouse=True)
def setup():
    setup_logging()
    init_db()
    # 清理测试数据
    with get_db() as conn:
        conn.execute("DELETE FROM hourly_kline WHERE code LIKE 'test%'")
        conn.execute("DELETE FROM realtime_snapshot WHERE code LIKE 'test%'")
        conn.execute("DELETE FROM screen_task WHERE id LIKE 'test%'")
    yield
    # 清理
    with get_db() as conn:
        conn.execute("DELETE FROM hourly_kline WHERE code LIKE 'test%'")
        conn.execute("DELETE FROM realtime_snapshot WHERE code LIKE 'test%'")
        conn.execute("DELETE FROM screen_task WHERE id LIKE 'test%'")


def _make_kline(n=50):
    dates = pd.date_range("2024-01-01", periods=n, freq="h")
    return pd.DataFrame({
        "date": dates,
        "open": np.random.rand(n) + 10,
        "high": np.random.rand(n) + 11,
        "low": np.random.rand(n) + 9,
        "close": np.random.rand(n) + 10,
        "volume": np.random.randint(1000, 10000, n).astype(float),
    })


class TestKlineCache:
    def test_save_and_load(self):
        df = _make_kline(20)
        save_kline("test001", df, "hourly_kline")
        loaded = load_kline("test001", "hourly_kline")
        assert len(loaded) == 20
        assert "close" in loaded.columns

    def test_load_empty(self):
        loaded = load_kline("nonexistent", "hourly_kline")
        assert loaded.empty

    def test_get_latest_date(self):
        df = _make_kline(10)
        save_kline("test002", df, "hourly_kline")
        latest = get_latest_cached_date("test002", "hourly_kline")
        assert latest is not None

    def test_get_cached_codes(self):
        df = _make_kline(5)
        save_kline("test003", df, "hourly_kline")
        codes = get_cached_codes("hourly_kline")
        assert "test003" in codes


class TestSnapshot:
    def test_save_and_load(self):
        df = pd.DataFrame([{
            "code": "test001", "name": "测试", "price": 10.5,
            "pct_change": 1.2, "change": 0.1, "volume": 10000,
            "amount": 100000, "high": 11, "low": 10, "open": 10.2,
            "pre_close": 10.3, "total_mv": 1000000, "circ_mv": 800000,
            "pe": 15.0, "pb": 1.5,
        }])
        save_snapshot(df)
        loaded = load_snapshot()
        assert len(loaded) >= 1
        assert loaded[loaded["code"] == "test001"].iloc[0]["price"] == 10.5

    def test_is_fresh_after_save(self):
        df = pd.DataFrame([{
            "code": "test002", "name": "测试2", "price": 20,
            "pct_change": 0, "change": 0, "volume": 100,
            "amount": 100, "high": 21, "low": 19, "open": 20,
            "pre_close": 20, "total_mv": 100, "circ_mv": 100,
            "pe": 10, "pb": 1,
        }])
        save_snapshot(df)
        assert is_snapshot_fresh()


class TestScreenTask:
    def test_save_and_load(self):
        save_screen_task("test_task1", "ma_combo", {"min_above": 4},
                         status="running", progress=50, total=100)
        task = load_screen_task("test_task1")
        assert task is not None
        assert task["strategy"] == "ma_combo"
        assert task["progress"] == 50

    def test_update_task(self):
        save_screen_task("test_task2", "ma_combo", {}, status="pending")
        save_screen_task("test_task2", "ma_combo", {}, status="completed",
                         progress=100, total=100, matched=10)
        task = load_screen_task("test_task2")
        assert task["status"] == "completed"
        assert task["matched"] == 10

    def test_list_tasks(self):
        save_screen_task("test_task3", "ma_combo", {}, status="completed")
        tasks = list_screen_tasks()
        assert len(tasks) > 0

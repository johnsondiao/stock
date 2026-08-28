"""SQLite 缓存层 - K线数据 + 行情快照的持久化缓存"""

import json
from datetime import datetime
import pandas as pd
from app.database import get_db
from app.config import settings
from app.log_config import get_logger

logger = get_logger(__name__)


# ── K线缓存 ──────────────────────────────────────────────

def load_kline(code: str, table: str = "hourly_kline") -> pd.DataFrame:
    """从 SQLite 加载缓存的K线数据"""
    with get_db() as conn:
        df = pd.read_sql_query(
            f"SELECT date, open, high, low, close, volume FROM {table} WHERE code = ? ORDER BY date",
            conn, params=(code,)
        )
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def save_kline(code: str, df: pd.DataFrame, table: str = "hourly_kline"):
    """将K线数据写入 SQLite 缓存（增量合并，按日期去重）"""
    if df.empty:
        return

    # 截断到最大缓存根数
    if len(df) > settings.kline_max_candles:
        df = df.tail(settings.kline_max_candles).reset_index(drop=True)

    with get_db() as conn:
        # 删除该股票的旧数据
        conn.execute(f"DELETE FROM {table} WHERE code = ?", (code,))

        # 批量插入
        rows = []
        for _, row in df.iterrows():
            date_str = row["date"].strftime("%Y-%m-%d %H:%M:%S") if hasattr(row["date"], "strftime") else str(row["date"])
            rows.append((code, date_str, row["open"], row["high"], row["low"], row["close"], row["volume"]))

        conn.executemany(
            f"INSERT OR REPLACE INTO {table} (code, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows
        )
    logger.debug("缓存 %s: %s %d 根K线", table, code, len(df))


def get_latest_cached_date(code: str, table: str = "hourly_kline") -> str | None:
    """获取缓存中最新的K线日期"""
    with get_db() as conn:
        row = conn.execute(
            f"SELECT MAX(date) as max_date FROM {table} WHERE code = ?", (code,)
        ).fetchone()
    return row["max_date"] if row and row["max_date"] else None


def get_cached_codes(table: str = "hourly_kline") -> set[str]:
    """获取缓存中有数据的所有股票代码"""
    with get_db() as conn:
        rows = conn.execute(f"SELECT DISTINCT code FROM {table}").fetchall()
    return {row["code"] for row in rows}


def get_cache_stats() -> dict:
    """获取缓存统计信息"""
    with get_db() as conn:
        hourly_count = conn.execute("SELECT COUNT(DISTINCT code) as cnt FROM hourly_kline").fetchone()["cnt"]
        daily_count = conn.execute("SELECT COUNT(DISTINCT code) as cnt FROM daily_kline").fetchone()["cnt"]
        snapshot_count = conn.execute("SELECT COUNT(*) as cnt FROM realtime_snapshot").fetchone()["cnt"]
        snapshot_time = conn.execute("SELECT MAX(updated_at) as t FROM realtime_snapshot").fetchone()["t"]

    return {
        "hourly_cached_stocks": hourly_count,
        "daily_cached_stocks": daily_count,
        "snapshot_stocks": snapshot_count,
        "snapshot_updated_at": snapshot_time,
    }


# ── 行情快照缓存 ──────────────────────────────────────────

def save_snapshot(df: pd.DataFrame):
    """保存实时行情快照到 SQLite"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        conn.execute("DELETE FROM realtime_snapshot")
        rows = []
        for _, row in df.iterrows():
            rows.append((
                row["code"], row.get("name", ""),
                row.get("price", 0), row.get("pct_change", 0), row.get("change", 0),
                row.get("volume", 0), row.get("amount", 0),
                row.get("high", 0), row.get("low", 0),
                row.get("open", 0), row.get("pre_close", 0),
                row.get("total_mv", 0), row.get("circ_mv", 0),
                row.get("pe", 0), row.get("pb", 0),
                now,
            ))
        conn.executemany(
            """INSERT INTO realtime_snapshot
               (code, name, price, pct_change, change, volume, amount,
                high, low, open, pre_close, total_mv, circ_mv, pe, pb, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows
        )
    logger.info("行情快照已保存: %d 只股票", len(df))


def load_snapshot() -> pd.DataFrame:
    """从 SQLite 加载行情快照"""
    with get_db() as conn:
        df = pd.read_sql_query("SELECT * FROM realtime_snapshot", conn)
    return df


def is_snapshot_fresh() -> bool:
    """检查行情快照是否在有效期内"""
    with get_db() as conn:
        row = conn.execute("SELECT MAX(updated_at) as t FROM realtime_snapshot").fetchone()
    if not row or not row["t"]:
        return False
    try:
        updated = datetime.strptime(row["t"], "%Y-%m-%d %H:%M:%S")
        age = (datetime.now() - updated).total_seconds()
        return age < settings.snapshot_ttl_seconds
    except ValueError:
        return False


# ── 选股任务 ──────────────────────────────────────────────

def save_screen_task(task_id: str, strategy: str, params: dict,
                     status: str = "pending", progress: int = 0,
                     total: int = 0, matched: int = 0,
                     skipped: int = 0, errors: int = 0,
                     result_json: str | None = None):
    """保存或更新选股任务"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM screen_task WHERE id = ?", (task_id,)).fetchone()
        if existing:
            conn.execute(
                """UPDATE screen_task SET status=?, progress=?, total=?, matched=?,
                   skipped=?, errors=?, result_json=?, updated_at=? WHERE id=?""",
                (status, progress, total, matched, skipped, errors, result_json, now, task_id)
            )
        else:
            conn.execute(
                """INSERT INTO screen_task
                   (id, strategy, params, status, progress, total, matched, skipped, errors, result_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (task_id, strategy, json.dumps(params, ensure_ascii=False),
                 status, progress, total, matched, skipped, errors, result_json, now, now)
            )


def load_screen_task(task_id: str) -> dict | None:
    """加载选股任务"""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM screen_task WHERE id = ?", (task_id,)).fetchone()
    if not row:
        return None
    return dict(row)


def list_screen_tasks(limit: int = 20) -> list[dict]:
    """列出最近的选股任务"""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM screen_task ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]

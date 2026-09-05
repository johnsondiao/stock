"""SQLite 数据库管理 - 建表、连接、上下文管理器"""

import sqlite3
import threading
from contextlib import contextmanager
from app.config import settings
from app.log_config import get_logger

logger = get_logger(__name__)

# 线程本地存储，每个线程一个连接
_local = threading.local()

_SCHEMA = """
-- 小时K线缓存
CREATE TABLE IF NOT EXISTS hourly_kline (
    code       TEXT    NOT NULL,
    date       TEXT    NOT NULL,
    open       REAL,
    high       REAL,
    low        REAL,
    close      REAL,
    volume     REAL,
    PRIMARY KEY (code, date)
);

-- 日K线缓存
CREATE TABLE IF NOT EXISTS daily_kline (
    code       TEXT    NOT NULL,
    date       TEXT    NOT NULL,
    open       REAL,
    high       REAL,
    low        REAL,
    close      REAL,
    volume     REAL,
    amount     REAL,
    PRIMARY KEY (code, date)
);

-- 5分钟K线缓存（双周期金叉策略用）
CREATE TABLE IF NOT EXISTS kline_5min (
    code       TEXT    NOT NULL,
    date       TEXT    NOT NULL,
    open       REAL,
    high       REAL,
    low        REAL,
    close      REAL,
    volume     REAL,
    PRIMARY KEY (code, date)
);

-- 实时行情快照
CREATE TABLE IF NOT EXISTS realtime_snapshot (
    code        TEXT PRIMARY KEY,
    name        TEXT,
    price       REAL,
    pct_change  REAL,
    change      REAL,
    volume      REAL,
    amount      REAL,
    high        REAL,
    low         REAL,
    open        REAL,
    pre_close   REAL,
    total_mv    REAL,
    circ_mv     REAL,
    pe          REAL,
    pb          REAL,
    updated_at  TEXT
);

-- 基本面估值(每日从新浪节点接口刷新一次)
CREATE TABLE IF NOT EXISTS fundamental (
    code        TEXT PRIMARY KEY,
    pe          REAL,
    pb          REAL,
    total_mv    REAL,
    updated_at  TEXT
);

-- 选股任务记录
CREATE TABLE IF NOT EXISTS screen_task (
    id          TEXT PRIMARY KEY,
    strategy    TEXT NOT NULL,
    params      TEXT,
    status      TEXT NOT NULL DEFAULT 'pending',
    progress    INTEGER DEFAULT 0,
    total       INTEGER DEFAULT 0,
    matched     INTEGER DEFAULT 0,
    skipped     INTEGER DEFAULT 0,
    errors      INTEGER DEFAULT 0,
    result_json TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_hourly_kline_code ON hourly_kline(code);
CREATE INDEX IF NOT EXISTS idx_daily_kline_code ON daily_kline(code);
CREATE INDEX IF NOT EXISTS idx_kline_5min_code ON kline_5min(code);
CREATE INDEX IF NOT EXISTS idx_screen_task_status ON screen_task(status);
CREATE INDEX IF NOT EXISTS idx_screen_task_created ON screen_task(created_at);
"""


def _get_connection() -> sqlite3.Connection:
    """获取当前线程的数据库连接（线程安全）"""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(str(settings.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn = conn
    return conn


@contextmanager
def get_db():
    """获取数据库连接的上下文管理器"""
    conn = _get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db():
    """初始化数据库表结构"""
    with get_db() as conn:
        conn.executescript(_SCHEMA)
    logger.info("数据库初始化完成: %s", settings.db_path)


def close_db():
    """关闭当前线程的数据库连接"""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None

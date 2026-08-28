"""行情服务 - 管理实时行情快照"""

from datetime import datetime
import pandas as pd
from app.data.provider import get_provider
from app.data import cache
from app.log_config import get_logger

logger = get_logger(__name__)


def refresh_snapshot(force: bool = False) -> pd.DataFrame:
    """
    刷新全市场行情快照

    :param force: 是否强制刷新（忽略缓存）
    :return: 全市场行情 DataFrame
    """
    provider = get_provider()
    return provider.get_all_stocks(force_refresh=force)


def get_snapshot() -> pd.DataFrame:
    """
    获取最新行情快照（优先读缓存）

    :return: 全市场行情 DataFrame
    """
    provider = get_provider()
    return provider.get_all_stocks(force_refresh=False)


def get_snapshot_info() -> dict:
    """获取行情快照的状态信息"""
    stats = cache.get_cache_stats()
    return {
        "stocks_count": stats["snapshot_stocks"],
        "updated_at": stats["snapshot_updated_at"],
        "is_fresh": cache.is_snapshot_fresh(),
    }

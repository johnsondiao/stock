"""统一数据提供者 - 聚合多数据源 + SQLite 缓存 + 增量更新"""

import pandas as pd
from app.data.sina import SinaSource
from app.data.akshare_source import AKShareSource
from app.data import cache
from app.data.rate_limiter import get_rate_limiter
from app.config import settings
from app.log_config import get_logger

logger = get_logger(__name__)


class DataProvider:
    """
    统一数据接口，聚合多个数据源并利用 SQLite 缓存。

    核心设计：
    - 实时行情: AKShare（一次请求获取全市场，含市值/PE/PB）→ 缓存到 SQLite
    - 小时K线: 新浪 API → 首次全量缓存，后续增量更新
    - 日K线: 新浪 API (scale=240) → 首次全量缓存，后续增量更新
    - 5分钟K线: 新浪 API (scale=5) → 双周期金叉策略入场信号用
    """

    def __init__(self):
        self._sina = SinaSource()
        self._akshare = AKShareSource()

    # ── 实时行情 ──────────────────────────────────────────

    def get_all_stocks(self, force_refresh: bool = False) -> pd.DataFrame:
        """
        获取全市场行情快照（含市值/PE/PB）
        优先读 SQLite 缓存（5分钟有效期），过期则刷新
        主数据源: 新浪 API（批量行情接口）
        """
        if not force_refresh and cache.is_snapshot_fresh():
            df = cache.load_snapshot()
            if not df.empty:
                logger.info("行情快照命中缓存: %d 只股票", len(df))
                return df

        # 从新浪 API 获取全市场行情
        df = self._sina.get_realtime_quotes()
        if not df.empty:
            cache.save_snapshot(df)
        return df

    # ── 小时K线（带缓存 + 增量更新） ─────────────────────

    def get_hourly_kline(self, code: str, min_candles: int = 170) -> pd.DataFrame:
        """
        获取小时K线数据（带 SQLite 缓存 + 增量更新）

        逻辑:
        1. 读 SQLite 缓存
        2. 如果缓存为空: 全量拉取 300 根并缓存
        3. 如果缓存已有但不足 min_candles: 全量拉取
        4. 如果缓存充足: 增量拉取最新 30 根，合并去重后缓存
        """
        cached = cache.load_kline(code, "hourly_kline")

        if cached.empty or len(cached) < min_candles:
            # 首次获取或数据不足: 全量拉取
            logger.debug("小时K线全量获取: %s", code)
            df = self._sina.get_kline(code, period="60", count=settings.kline_max_candles)
            if not df.empty:
                cache.save_kline(code, df, "hourly_kline")
            return df

        # 增量更新: 只拉最新 N 根
        logger.debug("小时K线增量获取: %s (缓存已有 %d 根)", code, len(cached))
        try:
            new_data = self._sina.get_kline(code, period="60", count=settings.kline_incremental_len)
            if new_data.empty:
                return cached

            # 合并去重
            merged = pd.concat([cached, new_data], ignore_index=True)
            merged = merged.drop_duplicates(subset=["date"], keep="last")
            merged = merged.sort_values("date").reset_index(drop=True)

            # 截断
            if len(merged) > settings.kline_max_candles:
                merged = merged.tail(settings.kline_max_candles).reset_index(drop=True)

            cache.save_kline(code, merged, "hourly_kline")
            return merged

        except Exception as e:
            logger.warning("小时K线增量获取失败 %s: %s, 返回缓存数据", code, e)
            return cached

    # ── 日K线（带缓存 + 增量更新） ───────────────────────

    def get_daily_kline(self, code: str, count: int = 300) -> pd.DataFrame:
        """
        获取日K线数据（带 SQLite 缓存）
        数据源: 新浪 API scale=240（AKShare 限流严重，已弃用）
        """
        cached = cache.load_kline(code, "daily_kline")

        if cached.empty or len(cached) < count * 0.5:
            logger.debug("日K线全量获取: %s", code)
            df = self._sina.get_kline(code, period="240", count=count)
            if not df.empty:
                cache.save_kline(code, df, "daily_kline")
            return df

        # 增量更新
        logger.debug("日K线增量获取: %s", code)
        try:
            new_data = self._sina.get_kline(code, period="240", count=30)
            if new_data.empty:
                return cached

            merged = pd.concat([cached, new_data], ignore_index=True)
            merged = merged.drop_duplicates(subset=["date"], keep="last")
            merged = merged.sort_values("date").reset_index(drop=True)

            if len(merged) > settings.kline_max_candles:
                merged = merged.tail(settings.kline_max_candles).reset_index(drop=True)

            cache.save_kline(code, merged, "daily_kline")
            return merged

        except Exception as e:
            logger.warning("日K线增量获取失败 %s: %s, 返回缓存数据", code, e)
            return cached

    # ── 缓存统计 ──────────────────────────────────────────

    def get_5min_kline(self, code: str, min_candles: int = 170) -> pd.DataFrame:
        """
        获取5分钟K线数据（带 SQLite 缓存 + 增量更新，双周期金叉策略用）
        300 根 ≈ 6 个交易日，足够计算 MA144 并检测近期金叉
        """
        cached = cache.load_kline(code, "kline_5min")

        if cached.empty or len(cached) < min_candles:
            logger.debug("5分钟K线全量获取: %s", code)
            df = self._sina.get_kline(code, period="5", count=settings.kline_max_candles)
            if not df.empty:
                cache.save_kline(code, df, "kline_5min")
            return df

        # 增量更新: 只拉最新 100 根（约 2 个交易日）
        logger.debug("5分钟K线增量获取: %s (缓存已有 %d 根)", code, len(cached))
        try:
            new_data = self._sina.get_kline(code, period="5", count=100)
            if new_data.empty:
                return cached

            merged = pd.concat([cached, new_data], ignore_index=True)
            merged = merged.drop_duplicates(subset=["date"], keep="last")
            merged = merged.sort_values("date").reset_index(drop=True)

            if len(merged) > settings.kline_max_candles:
                merged = merged.tail(settings.kline_max_candles).reset_index(drop=True)

            cache.save_kline(code, merged, "kline_5min")
            return merged

        except Exception as e:
            logger.warning("5分钟K线增量获取失败 %s: %s, 返回缓存数据", code, e)
            return cached

    def get_cache_stats(self) -> dict:
        """获取缓存统计信息"""
        return cache.get_cache_stats()


# 全局单例
_provider: DataProvider | None = None


def get_provider() -> DataProvider:
    """获取全局 DataProvider 实例"""
    global _provider
    if _provider is None:
        _provider = DataProvider()
    return _provider

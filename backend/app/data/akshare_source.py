"""AKShare 数据源 - 提供实时行情 + 日K线"""

from datetime import datetime, timedelta
import time
import akshare as ak
import pandas as pd
from app.data.base import DataSource
from app.data.rate_limiter import get_rate_limiter
from app.log_config import get_logger

logger = get_logger(__name__)


class AKShareSource(DataSource):
    """AKShare 数据源（实时行情 + 日K线）"""

    @property
    def name(self) -> str:
        return "akshare"

    def get_realtime_quotes(self, max_retries: int = 3) -> pd.DataFrame:
        """
        获取全市场实时行情快照（一次请求获取全部 A 股）
        返回标准格式 DataFrame，包含市值、PE、PB 等完整字段
        """
        limiter = get_rate_limiter()
        limiter.acquire()

        df = None
        for attempt in range(max_retries):
            try:
                logger.info("AKShare: 获取全市场实时行情... (第 %d 次)", attempt + 1)
                df = ak.stock_zh_a_spot_em()
                break
            except Exception as e:
                logger.warning("AKShare 获取行情失败 (第 %d 次): %s", attempt + 1, e)
                if attempt < max_retries - 1:
                    wait = 5 * (attempt + 1)
                    logger.info("等待 %d 秒后重试...", wait)
                    time.sleep(wait)
                else:
                    raise

        if df is None or df.empty:
            return pd.DataFrame()

        # 标准化列名
        col_map = {
            "代码": "code", "名称": "name", "最新价": "price",
            "涨跌幅": "pct_change", "涨跌额": "change",
            "成交量": "volume", "成交额": "amount",
            "最高": "high", "最低": "low",
            "今开": "open", "昨收": "pre_close",
            "总市值": "total_mv", "流通市值": "circ_mv",
            "市盈率-动态": "pe", "市净率": "pb",
        }
        result = df.rename(columns=col_map)

        # 只保留需要的列（缺少的列填 0）
        keep_cols = [
            "code", "name", "price", "pct_change", "change",
            "volume", "amount", "high", "low", "open", "pre_close",
            "total_mv", "circ_mv", "pe", "pb",
        ]
        for col in keep_cols:
            if col not in result.columns:
                result[col] = 0.0

        result = result[keep_cols].copy()

        # 过滤无效数据（价格为 0 或 NaN）
        result = result[result["price"].notna() & (result["price"] > 0)]

        # 成交量转为手（AKShare 返回的是股）
        result["volume"] = result["volume"] / 100

        logger.info("AKShare: 获取到 %d 只股票行情", len(result))
        return result.reset_index(drop=True)

    def get_kline(self, code: str, period: str = "daily", count: int = 300) -> pd.DataFrame:
        """
        获取日K线数据
        :param code: 股票代码
        :param period: "daily"/"weekly"/"monthly"
        :param count: 获取根数（通过日期范围间接控制）
        """
        limiter = get_rate_limiter()
        limiter.acquire()

        # 根据 count 估算需要的天数（日线约 1 根/天）
        days = max(count * 2, 365)
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        end_date = datetime.now().strftime("%Y%m%d")

        df = ak.stock_zh_a_hist(
            symbol=code, period=period,
            start_date=start_date, end_date=end_date, adjust="qfq"
        )

        if df.empty:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount"])

        col_map = {
            "日期": "date", "开盘": "open", "最高": "high",
            "最低": "low", "收盘": "close", "成交量": "volume",
            "成交额": "amount",
        }
        result = df.rename(columns=col_map)
        result["date"] = pd.to_datetime(result["date"])

        # 只保留需要的列
        keep = ["date", "open", "high", "low", "close", "volume"]
        if "amount" in result.columns:
            keep.append("amount")
        result = result[keep].tail(count).reset_index(drop=True)
        return result

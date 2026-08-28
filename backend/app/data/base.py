"""数据源抽象基类"""

from abc import ABC, abstractmethod
import pandas as pd


class DataSource(ABC):
    """数据源抽象基类，所有数据源实现必须遵循此接口"""

    @abstractmethod
    def get_realtime_quotes(self) -> pd.DataFrame:
        """
        获取全市场实时行情快照
        返回 DataFrame 列: code, name, price, pct_change, change, volume, amount,
                          high, low, open, pre_close, total_mv, circ_mv, pe, pb
        """

    @abstractmethod
    def get_kline(self, code: str, period: str = "60", count: int = 300) -> pd.DataFrame:
        """
        获取单只股票的K线数据
        :param code: 股票代码，如 "000001"
        :param period: 周期 "60"(1小时)/"30"/"15"/"5"/"daily"
        :param count: 获取根数
        返回 DataFrame 列: date, open, high, low, close, volume
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """数据源名称"""

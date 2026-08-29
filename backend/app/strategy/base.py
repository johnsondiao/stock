"""策略抽象基类 + 信号定义"""

from abc import ABC, abstractmethod
from enum import Enum
import pandas as pd


class Signal(str, Enum):
    """交易信号强度"""
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    NEUTRAL = "neutral"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


class Strategy(ABC):
    """
    策略抽象基类

    所有策略必须实现:
    - name: 策略唯一标识
    - description: 策略描述
    - params_schema: 参数 JSON Schema（供前端动态渲染表单）
    - evaluate(): 评估逻辑，输入K线数据 + 参数，输出信号 + 详情
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """策略唯一标识名"""

    @property
    @abstractmethod
    def description(self) -> str:
        """策略描述"""

    @property
    @abstractmethod
    def params_schema(self) -> dict:
        """
        参数 JSON Schema，用于前端动态渲染表单
        格式: {"field_name": {"type": "number", "label": "显示名", "default": 默认值, ...}}
        """

    @abstractmethod
    def evaluate(self, kline: pd.DataFrame, params: dict) -> dict:
        """
        评估策略

        :param kline: K线数据 DataFrame (date, open, high, low, close, volume)
        :param params: 策略参数
        :return: {
            "signal": Signal 枚举值,
            "score": 0-100 评分,
            "details": {策略特定的详细信息}
        }
        """

    @property
    def dual_timeframe(self) -> bool:
        """是否双周期策略（需 60 分钟闸门 + 5 分钟入场两阶段评估）"""
        return False

    def evaluate_gate(self, kline: pd.DataFrame, params: dict) -> dict:
        """双周期策略第一阶段: 大周期趋势闸门（默认不拦截）"""
        return {"passed": True, "details": {}}

    def evaluate_entry(self, kline_5min: pd.DataFrame, gate: dict, params: dict) -> dict:
        """双周期策略第二阶段: 小周期入场信号评估"""
        raise NotImplementedError

    def to_dict(self) -> dict:
        """序列化策略信息"""
        return {
            "name": self.name,
            "description": self.description,
            "params_schema": self.params_schema,
            "dual_timeframe": self.dual_timeframe,
        }

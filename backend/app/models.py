"""Pydantic 请求/响应模型"""

from pydantic import BaseModel, Field
from typing import Optional


class ConditionItem(BaseModel):
    """单条筛选条件"""
    field: str = Field(..., description="指标字段名，如 macd / rsi14 / k / ma5")
    operator: str = Field(..., description="比较运算符: gt / lt / gte / lte / between")
    value: float = Field(..., description="阈值")
    value2: Optional[float] = Field(None, description="between 时的上限")


class ScreenRequest(BaseModel):
    """选股请求"""
    conditions: list[ConditionItem] = Field(..., description="技术指标筛选条件列表")
    min_price: float = Field(0, description="最低股价")
    max_price: float = Field(99999, description="最高股价")
    min_volume: float = Field(0, description="最小成交量（手）")
    min_market_cap: float = Field(0, description="最小总市值（亿元）")
    exclude_st: bool = Field(True, description="排除 ST 股")
    lookback_days: int = Field(120, description="指标计算回看天数")


class ScreenResultItem(BaseModel):
    """单只选股结果"""
    code: str
    name: str
    price: float
    pct_change: float
    volume: float
    macd_dif: Optional[float] = None
    macd_dea: Optional[float] = None
    rsi: Optional[float] = None
    k: Optional[float] = None
    d: Optional[float] = None
    j: Optional[float] = None
    ma5: Optional[float] = None
    ma20: Optional[float] = None


class ScreenResponse(BaseModel):
    """选股响应"""
    total: int
    data: list[dict]
    message: str = "ok"


class StockHistoryResponse(BaseModel):
    """个股历史行情 + 指标"""
    code: str
    name: str
    data: list[dict]


class MAStrategyRequest(BaseModel):
    """MA 均线多头策略选股请求"""
    min_price: float = Field(0, description="最低股价")
    max_price: float = Field(99999, description="最高股价")
    min_volume: float = Field(0, description="最小成交量（手）")
    min_market_cap: float = Field(0, description="最小总市值（亿元）")
    exclude_st: bool = Field(True, description="排除 ST 股")
    min_above: int = Field(4, description="最少站上几条均线才开仓 (1-4)")

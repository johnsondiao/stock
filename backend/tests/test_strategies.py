"""测试策略逻辑"""

import pytest
import pandas as pd
import numpy as np
from app.strategy.base import Signal
from app.strategy.ma_bull import MABullStrategy
from app.strategy.macd_cross import MACDCrossStrategy


@pytest.fixture
def ma_strategy():
    return MABullStrategy()


@pytest.fixture
def macd_strategy():
    return MACDCrossStrategy()


@pytest.fixture
def bullish_kline():
    """生成上涨趋势K线（应该触发多头信号）"""
    np.random.seed(100)
    n = 250
    dates = pd.date_range("2024-01-01", periods=n, freq="h")
    # 明显上涨趋势
    close = 10 + np.linspace(0, 5, n) + np.random.randn(n) * 0.1
    return pd.DataFrame({
        "date": dates,
        "open": close - 0.05,
        "high": close + 0.1,
        "low": close - 0.1,
        "close": close,
        "volume": np.random.randint(1000, 10000, n).astype(float),
    })


@pytest.fixture
def bearish_kline():
    """生成下跌趋势K线"""
    np.random.seed(200)
    n = 250
    dates = pd.date_range("2024-01-01", periods=n, freq="h")
    close = 20 - np.linspace(0, 8, n) + np.random.randn(n) * 0.1
    return pd.DataFrame({
        "date": dates,
        "open": close + 0.05,
        "high": close + 0.1,
        "low": close - 0.1,
        "close": close,
        "volume": np.random.randint(1000, 10000, n).astype(float),
    })


class TestMABullStrategy:
    def test_name(self, ma_strategy):
        assert ma_strategy.name == "ma_bull"

    def test_params_schema(self, ma_strategy):
        schema = ma_strategy.params_schema
        assert "min_above" in schema
        assert "fresh_threshold" in schema

    def test_bullish_signal(self, ma_strategy, bullish_kline):
        result = ma_strategy.evaluate(bullish_kline, {"min_above": 4, "fresh_threshold": 20})
        assert result["score"] > 0
        assert result["details"]["above_count"] > 0

    def test_bearish_signal(self, ma_strategy, bearish_kline):
        result = ma_strategy.evaluate(bearish_kline, {"min_above": 4, "fresh_threshold": 4})
        # 下跌趋势不应该站上全部均线
        assert result["details"]["above_count"] < 4

    def test_insufficient_data(self, ma_strategy):
        short_df = pd.DataFrame({
            "date": range(10),
            "open": range(10),
            "high": range(10),
            "low": range(10),
            "close": range(10),
            "volume": range(10),
        })
        result = ma_strategy.evaluate(short_df, {})
        assert result["signal"] == Signal.NEUTRAL

    def test_fresh_candles_calculation(self, ma_strategy, bullish_kline):
        result = ma_strategy.evaluate(bullish_kline, {"min_above": 4, "fresh_threshold": 4})
        fresh = result["details"]["fresh_candles"]
        assert isinstance(fresh, int)
        assert fresh >= 0

    def test_to_dict(self, ma_strategy):
        d = ma_strategy.to_dict()
        assert "name" in d
        assert "description" in d
        assert "params_schema" in d


class TestMACDCrossStrategy:
    def test_name(self, macd_strategy):
        assert macd_strategy.name == "macd_cross"

    def test_evaluate_returns_signal(self, macd_strategy, bullish_kline):
        result = macd_strategy.evaluate(bullish_kline, {})
        assert "signal" in result
        assert "score" in result
        assert "details" in result

    def test_golden_cross_details(self, macd_strategy, bullish_kline):
        result = macd_strategy.evaluate(bullish_kline, {})
        details = result["details"]
        assert "dif" in details
        assert "dea" in details
        assert "golden_cross" in details
        assert "death_cross" in details

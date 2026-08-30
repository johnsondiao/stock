"""测试策略逻辑（当前仅组合策略 ma_combo）"""

import pytest
import pandas as pd
import numpy as np
from app.strategy.base import Signal
from app.strategy.ma_combo import MAComboStrategy


@pytest.fixture
def combo_strategy():
    return MAComboStrategy()


@pytest.fixture
def bullish_kline():
    """生成上涨趋势K线"""
    np.random.seed(100)
    n = 250
    dates = pd.date_range("2024-01-01", periods=n, freq="h")
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


class TestMAComboStrategy:
    def test_name(self, combo_strategy):
        assert combo_strategy.name == "ma_combo"

    def test_dual_timeframe(self, combo_strategy):
        assert combo_strategy.dual_timeframe is True

    def test_params_schema(self, combo_strategy):
        schema = combo_strategy.params_schema
        for key in ("min_above", "hourly_fast", "hourly_slow",
                    "min_fast", "min_slow", "hourly_lookback",
                    "min_lookback", "fresh_min_bars"):
            assert key in schema

    def test_gate_bearish_fails(self, combo_strategy, bearish_kline):
        """下跌趋势: 站上均线数不足, 闸门必须失败"""
        gate = combo_strategy.evaluate_gate(bearish_kline, {})
        assert gate["passed"] is False
        assert gate["details"]["above_count"] < 4

    def test_gate_structure(self, combo_strategy, bullish_kline):
        """闸门返回结构完整"""
        gate = combo_strategy.evaluate_gate(bullish_kline, {})
        assert "passed" in gate
        assert "details" in gate
        assert "above_count" in gate["details"]

    def test_entry_insufficient_data(self, combo_strategy, bullish_kline):
        """5分钟数据不足 MA288 时返回 NEUTRAL"""
        gate = {"passed": True, "details": {}}
        result = combo_strategy.evaluate_entry(bullish_kline.tail(50), gate, {})
        assert result["signal"] == Signal.NEUTRAL
        assert result["score"] == 0

    def test_evaluate_compatible(self, combo_strategy, bullish_kline):
        """单周期兼容接口返回完整结构"""
        result = combo_strategy.evaluate(bullish_kline, {})
        assert "signal" in result
        assert "score" in result
        assert "details" in result

    def test_insufficient_data(self, combo_strategy):
        short_df = pd.DataFrame({
            "date": range(10),
            "open": range(10),
            "high": range(10),
            "low": range(10),
            "close": range(10),
            "volume": range(10),
        })
        gate = combo_strategy.evaluate_gate(short_df, {})
        assert gate["passed"] is False

    def test_to_dict(self, combo_strategy):
        d = combo_strategy.to_dict()
        assert d["name"] == "ma_combo"
        assert "params_schema" in d
        assert d["dual_timeframe"] is True

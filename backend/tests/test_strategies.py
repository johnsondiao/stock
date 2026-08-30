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
    """生成先平后涨K线（含快线上穿慢线的真实金叉事件）"""
    np.random.seed(100)
    n = 250
    dates = pd.date_range("2024-01-01", periods=n, freq="h")
    flat = np.full(80, 10.0)
    rise = 10 + np.linspace(0, 5, n - 80)
    close = np.concatenate([flat, rise]) + np.random.randn(n) * 0.05
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


@pytest.fixture
def daily_uptrend():
    """日线上涨趋势: MA12 > MA60 成立"""
    np.random.seed(300)
    n = 200
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    close = 10 + np.linspace(0, 6, n) + np.random.randn(n) * 0.05
    return pd.DataFrame({
        "date": dates,
        "open": close - 0.05,
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
        for key in ("hourly_fast", "hourly_slow",
                    "min_fast", "min_slow", "hourly_lookback",
                    "min_lookback", "fresh_min_bars"):
            assert key in schema

    def test_gate_bearish_fails(self, combo_strategy, bearish_kline, daily_uptrend):
        """下跌趋势: 价格未站上快慢线, 闸门必须失败"""
        gate = combo_strategy.evaluate_gate(bearish_kline, {}, kline_daily=daily_uptrend)
        assert gate["passed"] is False
        assert "gate_reason" in gate["details"]

    def test_gate_no_daily_fails(self, combo_strategy, bullish_kline):
        """缺日线数据: 闸门失败"""
        gate = combo_strategy.evaluate_gate(bullish_kline, {"hourly_lookback": 200})
        assert gate["passed"] is False
        assert gate["details"]["gate_reason"] == "日线数据不足"

    def test_gate_full_pass(self, combo_strategy, bullish_kline, daily_uptrend):
        """60分钟多头+金叉(放宽窗口) + 日线MA12>MA60 → 闸门通过"""
        gate = combo_strategy.evaluate_gate(
            bullish_kline, {"hourly_lookback": 200}, kline_daily=daily_uptrend)
        assert gate["passed"] is True
        assert gate["details"]["hourly_cross_bars_ago"] is not None
        assert gate["details"]["daily_ma_fast"] > gate["details"]["daily_ma_slow"]

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

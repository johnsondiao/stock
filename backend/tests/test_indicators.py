"""测试技术指标计算"""

import pytest
import pandas as pd
import numpy as np
from app.strategy.indicators import calc_ma, calc_macd, calc_rsi, calc_kdj, calc_boll


@pytest.fixture
def sample_kline():
    """生成测试用K线数据"""
    np.random.seed(42)
    n = 100
    dates = pd.date_range("2024-01-01", periods=n, freq="h")
    close = 10 + np.cumsum(np.random.randn(n) * 0.1)
    return pd.DataFrame({
        "date": dates,
        "open": close + np.random.randn(n) * 0.05,
        "high": close + abs(np.random.randn(n) * 0.1),
        "low": close - abs(np.random.randn(n) * 0.1),
        "close": close,
        "volume": np.random.randint(1000, 10000, n).astype(float),
    })


class TestMA:
    def test_basic_ma(self, sample_kline):
        df = calc_ma(sample_kline.copy(), [5, 10])
        assert "ma5" in df.columns
        assert "ma10" in df.columns
        # 前4个 ma5 应该是 NaN
        assert df["ma5"].iloc[:4].isna().all()
        # 第5个开始有值
        assert pd.notna(df["ma5"].iloc[4])

    def test_ma_values正确(self):
        df = pd.DataFrame({"close": [1, 2, 3, 4, 5], "date": range(5)})
        result = calc_ma(df, [3])
        # MA3: NaN, NaN, 2.0, 3.0, 4.0
        assert pd.isna(result["ma3"].iloc[0])
        assert result["ma3"].iloc[2] == 2.0
        assert result["ma3"].iloc[4] == 4.0


class TestMACD:
    def test_macd_columns(self, sample_kline):
        df = calc_macd(sample_kline.copy())
        assert "dif" in df.columns
        assert "dea" in df.columns
        assert "macd" in df.columns

    def test_macd_no_nan_after_warmup(self, sample_kline):
        df = calc_macd(sample_kline.copy())
        # 前30根后应该没有 NaN
        assert not df["dif"].iloc[30:].isna().any()


class TestRSI:
    def test_rsi_range(self, sample_kline):
        df = calc_rsi(sample_kline.copy(), 14)
        assert "rsi14" in df.columns
        valid = df["rsi14"].dropna()
        assert (valid >= 0).all() and (valid <= 100).all()


class TestKDJ:
    def test_kdj_columns(self, sample_kline):
        df = calc_kdj(sample_kline.copy())
        assert "k" in df.columns
        assert "d" in df.columns
        assert "j" in df.columns

    def test_kdj_initial_value(self, sample_kline):
        df = calc_kdj(sample_kline.copy(), n=9)
        # 第9个位置（index=8）K 应该是 50
        assert df["k"].iloc[8] == 50.0


class TestBOLL:
    def test_boll_columns(self, sample_kline):
        df = calc_boll(sample_kline.copy())
        assert "boll_mid" in df.columns
        assert "boll_upper" in df.columns
        assert "boll_lower" in df.columns

    def test_boll_upper_above_lower(self, sample_kline):
        df = calc_boll(sample_kline.copy())
        valid = df.dropna(subset=["boll_upper", "boll_lower"])
        assert (valid["boll_upper"] > valid["boll_lower"]).all()

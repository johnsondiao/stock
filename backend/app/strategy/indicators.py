"""纯技术指标计算函数 - 不含任何策略逻辑"""

import pandas as pd
import numpy as np


def calc_ma(df: pd.DataFrame, periods: list[int] = None) -> pd.DataFrame:
    """计算简单移动平均线"""
    if periods is None:
        periods = [5, 10, 20, 60]
    for p in periods:
        df[f"ma{p}"] = df["close"].rolling(window=p).mean()
    return df


def calc_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """计算 MACD (DIF/DEA/柱状)"""
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    df["dif"] = ema_fast - ema_slow
    df["dea"] = df["dif"].ewm(span=signal, adjust=False).mean()
    df["macd"] = 2 * (df["dif"] - df["dea"])
    return df


def calc_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """计算 RSI"""
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df[f"rsi{period}"] = 100 - (100 / (1 + rs))
    return df


def calc_kdj(df: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3) -> pd.DataFrame:
    """计算 KDJ"""
    low_n = df["low"].rolling(window=n).min()
    high_n = df["high"].rolling(window=n).max()
    rsv = (df["close"] - low_n) / (high_n - low_n).replace(0, np.nan) * 100

    k = pd.Series(np.nan, index=df.index, dtype=float)
    d = pd.Series(np.nan, index=df.index, dtype=float)

    k.iloc[n - 1] = 50.0
    d.iloc[n - 1] = 50.0
    for i in range(n, len(df)):
        k.iloc[i] = (2 / m1) * k.iloc[i - 1] + (1 / m1) * rsv.iloc[i]
        d.iloc[i] = (2 / m2) * d.iloc[i - 1] + (1 / m2) * k.iloc[i]

    df["k"] = k
    df["d"] = d
    df["j"] = 3 * k - 2 * d
    return df


def calc_boll(df: pd.DataFrame, period: int = 20, std_dev: int = 2) -> pd.DataFrame:
    """计算布林带"""
    df["boll_mid"] = df["close"].rolling(window=period).mean()
    rolling_std = df["close"].rolling(window=period).std()
    df["boll_upper"] = df["boll_mid"] + std_dev * rolling_std
    df["boll_lower"] = df["boll_mid"] - std_dev * rolling_std
    return df


def calc_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """计算全部技术指标"""
    df = calc_ma(df)
    df = calc_macd(df)
    df = calc_rsi(df)
    df = calc_kdj(df)
    df = calc_boll(df)
    return df

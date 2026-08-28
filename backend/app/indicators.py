"""技术指标计算模块 - MACD / RSI / KDJ / 均线"""

import pandas as pd
import numpy as np


def calc_ma(df: pd.DataFrame, periods: list[int] = [5, 10, 20, 60]) -> pd.DataFrame:
    """计算移动平均线"""
    for p in periods:
        df[f"ma{p}"] = df["close"].rolling(window=p).mean()
    return df


def calc_ema(series: pd.Series, span: int) -> pd.Series:
    """指数移动平均"""
    return series.ewm(span=span, adjust=False).mean()


def calc_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """
    计算 MACD
    返回: DIF, DEA, MACD柱
    """
    ema_fast = calc_ema(df["close"], fast)
    ema_slow = calc_ema(df["close"], slow)
    df["dif"] = ema_fast - ema_slow
    df["dea"] = calc_ema(df["dif"], signal)
    df["macd"] = 2 * (df["dif"] - df["dea"])
    return df


def calc_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """计算 RSI 相对强弱指标"""
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df[f"rsi{period}"] = 100 - (100 / (1 + rs))
    return df


def calc_kdj(df: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3) -> pd.DataFrame:
    """
    计算 KDJ 随机指标
    """
    low_n = df["low"].rolling(window=n).min()
    high_n = df["high"].rolling(window=n).max()
    rsv = (df["close"] - low_n) / (high_n - low_n).replace(0, np.nan) * 100

    df["k"] = 50.0
    df["d"] = 50.0
    k_values = [50.0]
    d_values = [50.0]

    for i in range(1, len(rsv)):
        if np.isnan(rsv.iloc[i]):
            k_values.append(k_values[-1])
            d_values.append(d_values[-1])
        else:
            k = (m1 - 1) / m1 * k_values[-1] + 1 / m1 * rsv.iloc[i]
            d = (m2 - 1) / m2 * d_values[-1] + 1 / m2 * k
            k_values.append(k)
            d_values.append(d)

    df["k"] = k_values
    df["d"] = d_values
    df["j"] = 3 * df["k"] - 2 * df["d"]
    return df


def calc_boll(df: pd.DataFrame, period: int = 20, std_dev: int = 2) -> pd.DataFrame:
    """计算布林带"""
    df["boll_mid"] = df["close"].rolling(window=period).mean()
    rolling_std = df["close"].rolling(window=period).std()
    df["boll_upper"] = df["boll_mid"] + std_dev * rolling_std
    df["boll_lower"] = df["boll_mid"] - std_dev * rolling_std
    return df


def calc_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """一次性计算所有技术指标"""
    df = calc_ma(df)
    df = calc_macd(df)
    df = calc_rsi(df)
    df = calc_kdj(df)
    df = calc_boll(df)
    return df


# ── MA 均线多头策略 ─────────────────────────────────────

# 策略参数：1小时K线，MA12 / MA60 / MA144 / MA169
MA_STRATEGY_PERIODS = [12, 60, 144, 169]


def calc_ma_strategy(df: pd.DataFrame) -> pd.DataFrame:
    """
    计算 MA 均线多头策略所需指标
    使用参数: MA12, MA60, MA144, MA169
    返回添加了均线和判断字段的 DataFrame
    """
    df = calc_ma(df, periods=MA_STRATEGY_PERIODS)

    latest = df.iloc[-1]
    price = latest["close"]

    # 判断股价与每条均线的关系
    above_count = 0
    for p in MA_STRATEGY_PERIODS:
        col = f"ma{p}"
        ma_val = latest[col]
        above_col = f"above_ma{p}"
        if pd.notna(ma_val) and price > ma_val:
            df.loc[df.index[-1], above_col] = 1
            above_count += 1
        else:
            df.loc[df.index[-1], above_col] = 0

    # 站上均线数量
    df.loc[df.index[-1], "ma_above_count"] = above_count
    # 全部站上 = 开仓信号
    df.loc[df.index[-1], "open_signal"] = 1 if above_count == len(MA_STRATEGY_PERIODS) else 0

    # 均线多头排列判断: MA12 > MA60 > MA144 > MA169
    ma_vals = [latest.get(f"ma{p}") for p in MA_STRATEGY_PERIODS]
    if all(pd.notna(v) for v in ma_vals):
        is_aligned = all(ma_vals[i] >= ma_vals[i+1] for i in range(len(ma_vals)-1))
        df.loc[df.index[-1], "ma_aligned"] = 1 if is_aligned else 0
    else:
        df.loc[df.index[-1], "ma_aligned"] = 0

    return df


def check_ma_open_signal(df: pd.DataFrame) -> dict:
    """
    检查最新一根K线是否满足开仓条件
    额外计算“刚站上”信息：回看前几根K线，判断股价是刚突破还是早就站上
    返回详细判断信息
    """
    df = calc_ma_strategy(df)
    latest = df.iloc[-1]
    price = float(latest["close"])

    result = {
        "price": price,
        "above_count": int(latest["ma_above_count"]),
        "total_ma": len(MA_STRATEGY_PERIODS),
        "open_signal": bool(latest["open_signal"]),
        "ma_aligned": bool(latest["ma_aligned"]),
        "fresh_candles": 0,  # 连续站上全部均线的K线根数（含当前）
        "ma_details": [],
    }

    # 回看最近 20 根K线，计算连续站上全部均线的根数
    n_all_above = 0
    for i in range(len(df) - 1, max(len(df) - 21, -1), -1):
        row = df.iloc[i]
        all_above = True
        for p in MA_STRATEGY_PERIODS:
            ma_val = row.get(f"ma{p}")
            if pd.isna(ma_val) or row["close"] <= ma_val:
                all_above = False
                break
        if all_above:
            n_all_above += 1
        else:
            break
    result["fresh_candles"] = n_all_above

    for p in MA_STRATEGY_PERIODS:
        ma_val = latest.get(f"ma{p}")
        ma_val = round(float(ma_val), 4) if pd.notna(ma_val) else None
        above = bool(latest.get(f"above_ma{p}", 0))
        result["ma_details"].append({
            "period": p,
            "value": ma_val,
            "price_above": above,
            "deviation": round((price - ma_val) / ma_val * 100, 2) if ma_val else None,
        })

    return result

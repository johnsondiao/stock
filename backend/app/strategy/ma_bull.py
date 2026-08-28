"""MA 均线多头策略 - 1小时K线，MA12/MA60/MA144/MA169"""

import pandas as pd
from app.strategy.base import Strategy, Signal
from app.strategy.indicators import calc_ma

# 策略参数：1小时K线，MA12 / MA60 / MA144 / MA169
MA_PERIODS = [12, 60, 144, 169]


class MABullStrategy(Strategy):

    @property
    def name(self) -> str:
        return "ma_bull"

    @property
    def description(self) -> str:
        return "MA 均线多头策略：1小时K线，判断股价站上 MA12/MA60/MA144/MA169 的情况，全部站上为最强开仓信号"

    @property
    def params_schema(self) -> dict:
        return {
            "min_above": {
                "type": "integer",
                "label": "最少站上均线数",
                "default": 4,
                "min": 1,
                "max": 4,
                "description": "至少站上几条均线才视为开仓信号（4=全部站上）",
            },
            "fresh_threshold": {
                "type": "integer",
                "label": "新鲜信号阈值（K线根数）",
                "default": 4,
                "min": 1,
                "max": 20,
                "description": "连续站上均线的K线根数 <= 此值视为'刚站上'（1小时=1根）",
            },
        }

    def evaluate(self, kline: pd.DataFrame, params: dict) -> dict:
        """
        评估 MA 均线多头信号

        :param kline: 1小时K线数据
        :param params: {min_above: int, fresh_threshold: int}
        :return: {signal, score, details}
        """
        min_above = params.get("min_above", 4)
        fresh_threshold = params.get("fresh_threshold", 4)

        if len(kline) < max(MA_PERIODS) + 1:
            return {"signal": Signal.NEUTRAL, "score": 0, "details": {"error": "数据不足"}}

        # 计算均线
        df = calc_ma(kline.copy(), periods=MA_PERIODS)
        latest = df.iloc[-1]
        price = float(latest["close"])

        # 判断站上几条均线
        above_count = 0
        ma_details = []
        for p in MA_PERIODS:
            col = f"ma{p}"
            ma_val = latest[col]
            is_above = pd.notna(ma_val) and price > ma_val
            if is_above:
                above_count += 1
            ma_val_f = round(float(ma_val), 4) if pd.notna(ma_val) else None
            deviation = round((price - ma_val) / ma_val * 100, 2) if pd.notna(ma_val) and ma_val != 0 else None
            ma_details.append({
                "period": p,
                "value": ma_val_f,
                "price_above": is_above,
                "deviation": deviation,
            })

        # 均线多头排列: MA12 > MA60 > MA144 > MA169
        ma_vals = [latest.get(f"ma{p}") for p in MA_PERIODS]
        ma_aligned = all(
            pd.notna(ma_vals[i]) and pd.notna(ma_vals[i + 1]) and ma_vals[i] >= ma_vals[i + 1]
            for i in range(len(ma_vals) - 1)
        )

        # 新鲜度: 回看最近 20 根K线，连续站上全部均线的根数
        fresh_candles = self._calc_fresh_candles(df)

        # 信号判断
        if above_count >= min_above:
            if ma_aligned and fresh_candles <= fresh_threshold:
                signal = Signal.STRONG_BUY
                score = 95
            elif ma_aligned:
                signal = Signal.STRONG_BUY
                score = 85
            elif fresh_candles <= fresh_threshold:
                signal = Signal.BUY
                score = 80
            else:
                signal = Signal.BUY
                score = 60
        elif above_count >= 3:
            signal = Signal.NEUTRAL
            score = 30
        else:
            signal = Signal.NEUTRAL
            score = 0

        return {
            "signal": signal,
            "score": score,
            "details": {
                "above_count": above_count,
                "total_ma": len(MA_PERIODS),
                "ma_aligned": ma_aligned,
                "fresh_candles": fresh_candles,
                "ma_details": ma_details,
                "ma_values": {f"ma{p}": round(float(latest[f"ma{p}"]), 2) if pd.notna(latest[f"ma{p}"]) else None
                              for p in MA_PERIODS},
            },
        }

    @staticmethod
    def _calc_fresh_candles(df: pd.DataFrame, lookback: int = 20) -> int:
        """回看最近 N 根K线，计算连续站上全部均线的根数"""
        n_all_above = 0
        for i in range(len(df) - 1, max(len(df) - lookback - 1, -1), -1):
            row = df.iloc[i]
            all_above = True
            for p in MA_PERIODS:
                ma_val = row.get(f"ma{p}")
                if pd.isna(ma_val) or row["close"] <= ma_val:
                    all_above = False
                    break
            if all_above:
                n_all_above += 1
            else:
                break
        return n_all_above

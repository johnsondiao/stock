"""MACD 金叉策略 - 示例策略，展示如何扩展"""

import pandas as pd
from app.strategy.base import Strategy, Signal
from app.strategy.indicators import calc_macd


class MACDCrossStrategy(Strategy):

    @property
    def name(self) -> str:
        return "macd_cross"

    @property
    def description(self) -> str:
        return "MACD 金叉策略：DIF 上穿 DEA 为买入信号，下穿为卖出信号"

    @property
    def params_schema(self) -> dict:
        return {
            "fast": {
                "type": "integer",
                "label": "快线周期",
                "default": 12,
                "min": 2,
                "max": 50,
            },
            "slow": {
                "type": "integer",
                "label": "慢线周期",
                "default": 26,
                "min": 10,
                "max": 100,
            },
            "signal": {
                "type": "integer",
                "label": "信号线周期",
                "default": 9,
                "min": 2,
                "max": 50,
            },
        }

    def evaluate(self, kline: pd.DataFrame, params: dict) -> dict:
        fast = params.get("fast", 12)
        slow = params.get("slow", 26)
        signal = params.get("signal", 9)

        if len(kline) < slow + signal:
            return {"signal": Signal.NEUTRAL, "score": 0, "details": {"error": "数据不足"}}

        df = calc_macd(kline.copy(), fast=fast, slow=slow, signal=signal)

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        dif = float(latest["dif"])
        dea = float(latest["dea"])
        macd_val = float(latest["macd"])
        prev_dif = float(prev["dif"])
        prev_dea = float(prev["dea"])

        # 金叉: 前一根 DIF < DEA, 当前 DIF > DEA
        golden_cross = prev_dif <= prev_dea and dif > dea
        # 死叉: 前一根 DIF > DEA, 当前 DIF < DEA
        death_cross = prev_dif >= prev_dea and dif < dea

        # DIF 在零轴上方/下方
        above_zero = dif > 0

        if golden_cross and above_zero:
            sig = Signal.STRONG_BUY
            score = 90
        elif golden_cross:
            sig = Signal.BUY
            score = 75
        elif death_cross:
            sig = Signal.SELL
            score = 20
        elif dif > dea and above_zero:
            sig = Signal.NEUTRAL
            score = 50
        else:
            sig = Signal.NEUTRAL
            score = 40

        return {
            "signal": sig,
            "score": score,
            "details": {
                "dif": round(dif, 4),
                "dea": round(dea, 4),
                "macd": round(macd_val, 4),
                "golden_cross": golden_cross,
                "death_cross": death_cross,
                "above_zero": above_zero,
            },
        }

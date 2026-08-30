"""双周期均线金叉策略 - 60分钟定方向 + 5分钟定时机（均线周期可配置）

来源: 双周期共振交易法，支持两套参数:
- 期货原版: 60分钟 MA24 金叉 MA60，5分钟 MA12 金叉 MA288
  (换算: 5分钟 x 288根 = 1440分钟 = 60分钟 x 24根)
- 股票折半版(默认): 60分钟 MA12 金叉 MA60，5分钟 MA12 金叉 MA144
  (股票日交易时长是期货的一半，周期折半)
- 出场: 60分钟趋势破坏(价格跌破均线/均线死叉)时离场
- 仓位: 开仓后分批止盈, 留底仓跑趋势
"""

import pandas as pd
from app.strategy.base import Strategy, Signal
from app.strategy.indicators import calc_ma

# 默认参数: 股票折半版（可通过 params 覆盖为期货版 24/60 + 12/288）
DEFAULT_HOURLY_FAST = 12
DEFAULT_HOURLY_SLOW = 60
DEFAULT_MIN_FAST = 12
DEFAULT_MIN_SLOW = 144


class MACrossDualStrategy(Strategy):

    @property
    def name(self) -> str:
        return "ma_cross_dual"

    @property
    def description(self) -> str:
        return ("双周期均线金叉策略：60分钟快线金叉慢线定方向，"
                "5分钟快线金叉长周期线定入场时机，大小周期共振开仓（均线周期可配置）")

    @property
    def dual_timeframe(self) -> bool:
        return True

    @property
    def params_schema(self) -> dict:
        return {
            "hourly_fast": {
                "type": "integer",
                "label": "60分钟快线周期",
                "default": 12,
                "min": 2,
                "max": 60,
                "description": "60分钟快线(股票版12/期货版24)",
            },
            "hourly_slow": {
                "type": "integer",
                "label": "60分钟慢线周期",
                "default": 60,
                "min": 10,
                "max": 200,
                "description": "60分钟慢线(默认60)",
            },
            "min_fast": {
                "type": "integer",
                "label": "5分钟快线周期",
                "default": 12,
                "min": 2,
                "max": 60,
                "description": "5分钟快线(默认12)",
            },
            "min_slow": {
                "type": "integer",
                "label": "5分钟慢线周期",
                "default": 144,
                "min": 10,
                "max": 400,
                "description": "5分钟慢线(股票版144/期货版288，288根=60分钟的24根)",
            },
            "hourly_lookback": {
                "type": "integer",
                "label": "60分钟金叉确认窗口(根)",
                "default": 8,
                "min": 1,
                "max": 40,
                "description": "60分钟 MA12 上穿 MA60 必须发生在最近 N 根K线内(8根=2个交易日)",
            },
            "min_lookback": {
                "type": "integer",
                "label": "5分钟入场信号窗口(根)",
                "default": 48,
                "min": 1,
                "max": 200,
                "description": "5分钟 MA12 上穿 MA144 必须发生在最近 N 根K线内(48根=1个交易日)",
            },
            "fresh_min_bars": {
                "type": "integer",
                "label": "新鲜金叉阈值(5分钟根数)",
                "default": 12,
                "min": 1,
                "max": 48,
                "description": "5分钟金叉距今 <= 此值视为新鲜入场点(12根=1小时)",
            },
        }

    # ── 第一阶段: 60分钟趋势闸门 ──────────────────────────

    def evaluate_gate(self, kline: pd.DataFrame, params: dict) -> dict:
        """
        60分钟闸门: 当前快线 > 慢线，且金叉发生在最近 hourly_lookback 根内
        """
        hourly_fast = params.get("hourly_fast", DEFAULT_HOURLY_FAST)
        hourly_slow = params.get("hourly_slow", DEFAULT_HOURLY_SLOW)
        hourly_lookback = params.get("hourly_lookback", 8)

        if len(kline) < hourly_slow + 2:
            return {"passed": False, "details": {"gate_reason": "数据不足"}}

        df = calc_ma(kline.copy(), periods=[hourly_fast, hourly_slow])
        fast_col, slow_col = f"ma{hourly_fast}", f"ma{hourly_slow}"

        latest = df.iloc[-1]
        if pd.isna(latest[fast_col]) or pd.isna(latest[slow_col]):
            return {"passed": False, "details": {"gate_reason": "均线数据不足"}}

        # 当前必须保持多头状态（趋势未破坏）
        if latest[fast_col] <= latest[slow_col]:
            return {"passed": False, "details": {"gate_reason": "60分钟未保持多头"}}

        cross_ago = self._bars_since_cross(df, fast_col, slow_col)
        gate_details = {
            "hourly_cross_bars_ago": cross_ago,
            "hourly_ma_fast": round(float(latest[fast_col]), 4),
            "hourly_ma_slow": round(float(latest[slow_col]), 4),
        }

        # 金叉必须发生在确认窗口内
        if cross_ago is None or cross_ago >= hourly_lookback:
            return {"passed": False, "details": gate_details}

        return {"passed": True, "details": gate_details}

    # ── 第二阶段: 5分钟入场信号 ──────────────────────────

    def evaluate_entry(self, kline_5min: pd.DataFrame, gate: dict, params: dict) -> dict:
        """
        5分钟入场: 快线上穿长周期线金叉，结合 60 分钟闸门结果给出信号
        """
        min_fast = params.get("min_fast", DEFAULT_MIN_FAST)
        min_slow = params.get("min_slow", DEFAULT_MIN_SLOW)
        min_lookback = params.get("min_lookback", 48)
        fresh_bars = params.get("fresh_min_bars", 12)

        if len(kline_5min) < min_slow + 2:
            return {"signal": Signal.NEUTRAL, "score": 0,
                    "details": {"error": "5分钟数据不足", **gate.get("details", {})}}

        df = calc_ma(kline_5min.copy(), periods=[min_fast, min_slow])
        fast_col, slow_col = f"ma{min_fast}", f"ma{min_slow}"

        latest = df.iloc[-1]
        price = float(latest["close"])
        details = dict(gate.get("details", {}))

        if pd.isna(latest[fast_col]) or pd.isna(latest[slow_col]):
            return {"signal": Signal.NEUTRAL, "score": 0,
                    "details": {"error": "5分钟均线数据不足", **details}}

        cross_ago = self._bars_since_cross(df, fast_col, slow_col)
        details.update({
            "min_cross_bars_ago": cross_ago,
            "min_ma_fast": round(float(latest[fast_col]), 4),
            "min_ma_slow": round(float(latest[slow_col]), 4),
            "price": price,
        })

        # 当前未保持多头 → 入场条件不成立
        if latest[fast_col] <= latest[slow_col]:
            return {"signal": Signal.NEUTRAL, "score": 0, "details": details}

        # 金叉必须在信号窗口内
        if cross_ago is None or cross_ago >= min_lookback:
            return {"signal": Signal.NEUTRAL, "score": 0, "details": details}

        # ── 打分: 大小周期共振强度 ──
        hourly_ago = gate["details"].get("hourly_cross_bars_ago")
        hourly_fresh = hourly_ago is not None and hourly_ago <= 4   # 60分钟刚金叉(1天内)
        min_fresh = cross_ago <= fresh_bars                          # 5分钟刚金叉(1小时内)
        price_above = price > latest[fast_col]                       # 价格站上快线

        if hourly_fresh and min_fresh and price_above:
            signal, score = Signal.STRONG_BUY, 95   # 完美共振: 双周期刚金叉+价格确认
        elif min_fresh and price_above:
            signal, score = Signal.STRONG_BUY, 88   # 5分钟新金叉+价格确认
        elif min_fresh:
            signal, score = Signal.BUY, 75          # 5分钟新金叉但价格未站上
        else:
            signal, score = Signal.BUY, 62          # 金叉较早, 信号已发酵

        details["hourly_fresh"] = hourly_fresh
        details["min_fresh"] = min_fresh
        return {"signal": signal, "score": score, "details": details}

    # ── 兼容单周期接口（仅评估60分钟趋势状态） ──────────

    def evaluate(self, kline: pd.DataFrame, params: dict) -> dict:
        gate = self.evaluate_gate(kline, params)
        if gate["passed"]:
            return {"signal": Signal.BUY, "score": 40, "details": gate["details"]}
        return {"signal": Signal.NEUTRAL, "score": 0, "details": gate["details"]}

    @staticmethod
    def _bars_since_cross(df: pd.DataFrame, fast_col: str, slow_col: str) -> int | None:
        """
        回看最近 200 根，返回快线上穿慢线后经过的K线数
        返回 None 表示窗口内没找到金叉（金叉更早发生或从未发生）
        """
        lookback = min(200, len(df) - 1)
        for i in range(len(df) - 1, len(df) - 1 - lookback, -1):
            cur, prev = df.iloc[i], df.iloc[i - 1]
            if pd.isna(cur[fast_col]) or pd.isna(prev[slow_col]):
                continue
            if cur[fast_col] > cur[slow_col] and prev[fast_col] <= prev[slow_col]:
                return len(df) - 1 - i
        return None

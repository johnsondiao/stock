"""组合策略: 多周期均线共振（60分钟定方向 + 日线确认趋势 + 5分钟定入场）

四段漏斗:
1. 60分钟状态: 价格站上快线(默认MA24)与慢线(默认MA60)
2. 60分钟金叉: 快线上穿慢线, 且刚发生不久 → 方向确认
3. 日线趋势: 日线 MA12 > MA60 → 大级别趋势确认
4. 5分钟入场: 快线(默认MA12)上穿长周期线(默认MA288) → 扣动扳机

参数换算: 5分钟 x 288根 = 1440分钟 = 60分钟 x 24根
股票折半版: 60分钟 12/60 + 5分钟 12/144 (股票日交易时长约为期货一半)
"""

import pandas as pd
from app.strategy.base import Strategy, Signal
from app.strategy.indicators import calc_ma

# 默认金叉参数: 期货原版 (可通过 params 覆盖为折半版)
DEFAULT_HOURLY_FAST = 24
DEFAULT_HOURLY_SLOW = 60
DEFAULT_MIN_FAST = 12
DEFAULT_MIN_SLOW = 288

# 日线趋势确认: MA12 > MA60 (固定)
DAILY_FAST = 12
DAILY_SLOW = 60


class MAComboStrategy(Strategy):

    @property
    def name(self) -> str:
        return "ma_combo"

    @property
    def description(self) -> str:
        return ("组合策略：60分钟价格站上快慢线 + 60分钟金叉定方向 + "
                "日线MA12>MA60确认趋势 + 5分钟金叉定入场，四段漏斗共振开仓")

    @property
    def dual_timeframe(self) -> bool:
        return True

    @property
    def params_schema(self) -> dict:
        return {
            "hourly_fast": {
                "type": "integer",
                "label": "60分钟快线周期",
                "default": 24,
                "min": 2,
                "max": 60,
                "description": "60分钟快线(期货版24/折半版12)",
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
                "default": 288,
                "min": 10,
                "max": 400,
                "description": "5分钟慢线(期货版288/折半版144)",
            },
            "hourly_lookback": {
                "type": "integer",
                "label": "60分钟金叉窗口(根)",
                "default": 8,
                "min": 1,
                "max": 40,
                "description": "60分钟金叉必须发生在最近N根内(8根=2个交易日)",
            },
            "min_lookback": {
                "type": "integer",
                "label": "5分钟金叉窗口(根)",
                "default": 48,
                "min": 1,
                "max": 200,
                "description": "5分钟金叉必须发生在最近N根内(48根=1个交易日)",
            },
            "fresh_min_bars": {
                "type": "integer",
                "label": "新鲜金叉阈值(5分钟根数)",
                "default": 12,
                "min": 1,
                "max": 48,
                "description": "5分钟金叉距今<=此值视为新鲜入场点(12根=1小时)",
            },
        }

    # ── 闸门: 60分钟状态 + 60分钟金叉 + 日线趋势 ──────────

    def evaluate_gate(self, kline: pd.DataFrame, params: dict,
                      kline_daily: pd.DataFrame | None = None) -> dict:
        """
        三段闸门（全部通过才放行）:
        A. 60分钟: 当前价站上快线与慢线
        B. 60分钟: 当前快线 > 慢线, 且金叉发生在最近 hourly_lookback 根内
        C. 日线:   MA12 > MA60 (趋势确认)
        """
        hourly_fast = params.get("hourly_fast", DEFAULT_HOURLY_FAST)
        hourly_slow = params.get("hourly_slow", DEFAULT_HOURLY_SLOW)
        hourly_lookback = params.get("hourly_lookback", 8)

        need = hourly_slow + 2
        if len(kline) < need:
            return {"passed": False, "details": {"gate_reason": "60分钟数据不足"}}

        df = calc_ma(kline.copy(), periods=[hourly_fast, hourly_slow])
        fast_col, slow_col = f"ma{hourly_fast}", f"ma{hourly_slow}"
        latest = df.iloc[-1]
        price = float(latest["close"])

        gate_details = {
            "hourly_ma_fast": round(float(latest[fast_col]), 4) if pd.notna(latest[fast_col]) else None,
            "hourly_ma_slow": round(float(latest[slow_col]), 4) if pd.notna(latest[slow_col]) else None,
        }

        # ── A. 价格站上快慢线 ──
        if pd.isna(latest[fast_col]) or pd.isna(latest[slow_col]):
            gate_details["gate_reason"] = "均线数据不足"
            return {"passed": False, "details": gate_details}
        if not (price > latest[fast_col] and price > latest[slow_col]):
            gate_details["gate_reason"] = "价格未站上60分钟快慢线"
            return {"passed": False, "details": gate_details}

        # ── B. 60分钟金叉 ──
        if latest[fast_col] <= latest[slow_col]:
            gate_details["gate_reason"] = "60分钟金叉后未保持多头"
            return {"passed": False, "details": gate_details}

        cross_ago = self._bars_since_cross(df, fast_col, slow_col)
        gate_details["hourly_cross_bars_ago"] = cross_ago
        if cross_ago is None or cross_ago >= hourly_lookback:
            gate_details["gate_reason"] = "60分钟金叉太早或不存在"
            return {"passed": False, "details": gate_details}

        # ── C. 日线趋势确认: MA12 > MA60 ──
        if kline_daily is None or len(kline_daily) < DAILY_SLOW + 2:
            gate_details["gate_reason"] = "日线数据不足"
            return {"passed": False, "details": gate_details}

        dd = calc_ma(kline_daily.copy(), periods=[DAILY_FAST, DAILY_SLOW])
        d_latest = dd.iloc[-1]
        d_fast, d_slow = d_latest[f"ma{DAILY_FAST}"], d_latest[f"ma{DAILY_SLOW}"]
        gate_details["daily_ma_fast"] = round(float(d_fast), 4) if pd.notna(d_fast) else None
        gate_details["daily_ma_slow"] = round(float(d_slow), 4) if pd.notna(d_slow) else None

        if pd.isna(d_fast) or pd.isna(d_slow) or d_fast <= d_slow:
            gate_details["gate_reason"] = "日线MA12未上穿MA60, 趋势未确认"
            return {"passed": False, "details": gate_details}

        return {"passed": True, "details": gate_details}

    # ── 入场: 5分钟金叉 ──────────────────────────────────

    def evaluate_entry(self, kline_5min: pd.DataFrame, gate: dict, params: dict) -> dict:
        """
        5分钟入场: 快线上穿长周期线金叉, 结合闸门结果打分
        """
        min_fast = params.get("min_fast", DEFAULT_MIN_FAST)
        min_slow = params.get("min_slow", DEFAULT_MIN_SLOW)
        min_lookback = params.get("min_lookback", 48)
        fresh_bars = params.get("fresh_min_bars", 12)

        details = dict(gate.get("details", {}))

        if len(kline_5min) < min_slow + 2:
            return {"signal": Signal.NEUTRAL, "score": 0,
                    "details": {"error": "5分钟数据不足", **details}}

        df = calc_ma(kline_5min.copy(), periods=[min_fast, min_slow])
        fast_col, slow_col = f"ma{min_fast}", f"ma{min_slow}"

        latest = df.iloc[-1]
        price = float(latest["close"])

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

        # 当前必须保持多头
        if latest[fast_col] <= latest[slow_col]:
            return {"signal": Signal.NEUTRAL, "score": 0, "details": details}

        # 金叉必须在信号窗口内
        if cross_ago is None or cross_ago >= min_lookback:
            return {"signal": Signal.NEUTRAL, "score": 0, "details": details}

        # ── 打分: 共振新鲜度 ──
        hourly_ago = details.get("hourly_cross_bars_ago")
        hourly_fresh = hourly_ago is not None and hourly_ago <= 4
        min_fresh = cross_ago <= fresh_bars
        price_above = price > latest[fast_col]

        if hourly_fresh and min_fresh and price_above:
            signal, score = Signal.STRONG_BUY, 98   # 双周期刚金叉 + 价格确认
        elif min_fresh and price_above:
            signal, score = Signal.STRONG_BUY, 90   # 5分钟新入场点 + 价格确认
        elif min_fresh:
            signal, score = Signal.BUY, 75          # 5分钟新金叉, 价格未确认
        else:
            signal, score = Signal.BUY, 62          # 金叉较早, 趋势进行中

        details["hourly_fresh"] = hourly_fresh
        details["min_fresh"] = min_fresh
        return {"signal": signal, "score": score, "details": details}

    # ── 兼容单周期接口（仅60分钟部分） ────────────────────

    def evaluate(self, kline: pd.DataFrame, params: dict) -> dict:
        gate = self.evaluate_gate(kline, params, kline_daily=None)
        if gate["passed"]:
            return {"signal": Signal.BUY, "score": 40, "details": gate["details"]}
        return {"signal": Signal.NEUTRAL, "score": 0, "details": gate["details"]}

    @staticmethod
    def _bars_since_cross(df: pd.DataFrame, fast_col: str, slow_col: str) -> int | None:
        """回看最近200根, 返回快线上穿慢线后经过的K线数; None=窗口内无金叉"""
        lookback = min(200, len(df) - 1)
        for i in range(len(df) - 1, len(df) - 1 - lookback, -1):
            cur, prev = df.iloc[i], df.iloc[i - 1]
            if pd.isna(cur[fast_col]) or pd.isna(prev[slow_col]):
                continue
            if cur[fast_col] > cur[slow_col] and prev[fast_col] <= prev[slow_col]:
                return len(df) - 1 - i
        return None

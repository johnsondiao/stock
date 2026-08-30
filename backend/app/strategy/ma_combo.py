"""组合策略: 多均线多头(定强弱) × 双周期金叉(定买卖点)

设计思想:
- 多均线策略回答"哪只股票强": 股价站上全部均线 + 均线多头排列 = 强势趋势状态
- 双周期金叉策略回答"什么时候买": 60分钟金叉确认方向, 5分钟金叉触发入场
- 组合后三段漏斗: 先确认趋势状态(空间), 再确认趋势刚转多(拐点), 最后精确入场(时机)

三段漏斗:
1. 60分钟多均线状态: 价格站上 MA12/MA60/MA144/MA169 (至少 min_above 条) + 可选多头排列
2. 60分钟金叉闸门: 快线(默认MA24)上穿慢线(默认MA60), 且刚发生不久 → 趋势刚转多
3. 5分钟金叉入场: 快线(默认MA12)上穿长周期线(默认MA288), 扣动扳机
"""

import pandas as pd
from app.strategy.base import Strategy, Signal
from app.strategy.indicators import calc_ma

# 多均线状态检查用的四条均线
STATE_MA_PERIODS = [12, 60, 144, 169]

# 默认金叉参数: 期货原版 (60分钟24/60 + 5分钟12/288)
DEFAULT_HOURLY_FAST = 24
DEFAULT_HOURLY_SLOW = 60
DEFAULT_MIN_FAST = 12
DEFAULT_MIN_SLOW = 288


class MAComboStrategy(Strategy):

    @property
    def name(self) -> str:
        return "ma_combo"

    @property
    def description(self) -> str:
        return ("组合策略：多均线多头定强弱（站上全部均线+多头排列）× "
                "双周期金叉定买卖点（60分钟定方向+5分钟定时机），三段漏斗共振开仓")

    @property
    def dual_timeframe(self) -> bool:
        return True

    @property
    def params_schema(self) -> dict:
        return {
            "min_above": {
                "type": "integer",
                "label": "最少站上均线数",
                "default": 4,
                "min": 1,
                "max": 4,
                "description": "60分钟收盘价至少站上几条均线(4=全部站上)",
            },
            "hourly_fast": {
                "type": "integer",
                "label": "60分钟金叉快线",
                "default": 24,
                "min": 2,
                "max": 60,
                "description": "60分钟金叉快线(期货版24/折半版12)",
            },
            "hourly_slow": {
                "type": "integer",
                "label": "60分钟金叉慢线",
                "default": 60,
                "min": 10,
                "max": 200,
                "description": "60分钟金叉慢线(默认60)",
            },
            "min_fast": {
                "type": "integer",
                "label": "5分钟金叉快线",
                "default": 12,
                "min": 2,
                "max": 60,
                "description": "5分钟金叉快线(默认12)",
            },
            "min_slow": {
                "type": "integer",
                "label": "5分钟金叉慢线",
                "default": 288,
                "min": 10,
                "max": 400,
                "description": "5分钟金叉慢线(期货版288/折半版144)",
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

    # ── 第一段 + 第二段: 60分钟 多均线状态 + 金叉闸门 ──────

    def evaluate_gate(self, kline: pd.DataFrame, params: dict) -> dict:
        """
        60分钟闸门（两个条件都要满足）:
        A. 多均线状态: 站上均线数 >= min_above
        B. 金叉确认: 当前快线 > 慢线, 且金叉发生在最近 hourly_lookback 根内
        """
        min_above = params.get("min_above", 4)
        hourly_fast = params.get("hourly_fast", DEFAULT_HOURLY_FAST)
        hourly_slow = params.get("hourly_slow", DEFAULT_HOURLY_SLOW)
        hourly_lookback = params.get("hourly_lookback", 8)

        need = max(hourly_slow, max(STATE_MA_PERIODS)) + 2
        if len(kline) < need:
            return {"passed": False, "details": {"gate_reason": "数据不足"}}

        periods = sorted(set(STATE_MA_PERIODS + [hourly_fast, hourly_slow]))
        df = calc_ma(kline.copy(), periods=periods)
        latest = df.iloc[-1]
        price = float(latest["close"])

        # ── 条件A: 多均线状态 ──
        above_count = 0
        for p in STATE_MA_PERIODS:
            ma_val = latest[f"ma{p}"]
            if pd.notna(ma_val) and price > ma_val:
                above_count += 1

        # 均线多头排列: MA12 > MA60 > MA144 > MA169
        ma_vals = [latest.get(f"ma{p}") for p in STATE_MA_PERIODS]
        ma_aligned = all(
            pd.notna(ma_vals[i]) and pd.notna(ma_vals[i + 1]) and ma_vals[i] >= ma_vals[i + 1]
            for i in range(len(ma_vals) - 1)
        )

        gate_details = {
            "above_count": above_count,
            "total_ma": len(STATE_MA_PERIODS),
            "ma_aligned": ma_aligned,
        }

        if above_count < min_above:
            gate_details["gate_reason"] = f"仅站上{above_count}条均线(<{min_above})"
            return {"passed": False, "details": gate_details}

        # ── 条件B: 金叉闸门 ──
        fast_col, slow_col = f"ma{hourly_fast}", f"ma{hourly_slow}"
        if pd.isna(latest[fast_col]) or pd.isna(latest[slow_col]):
            gate_details["gate_reason"] = "金叉均线数据不足"
            return {"passed": False, "details": gate_details}

        if latest[fast_col] <= latest[slow_col]:
            gate_details["gate_reason"] = "60分钟金叉后未保持多头"
            return {"passed": False, "details": gate_details}

        cross_ago = self._bars_since_cross(df, fast_col, slow_col)
        gate_details["hourly_cross_bars_ago"] = cross_ago
        gate_details["hourly_ma_fast"] = round(float(latest[fast_col]), 4)
        gate_details["hourly_ma_slow"] = round(float(latest[slow_col]), 4)

        if cross_ago is None or cross_ago >= hourly_lookback:
            gate_details["gate_reason"] = "60分钟金叉太早或不存在"
            return {"passed": False, "details": gate_details}

        return {"passed": True, "details": gate_details}

    # ── 第三段: 5分钟金叉入场 ──────────────────────────────

    def evaluate_entry(self, kline_5min: pd.DataFrame, gate: dict, params: dict) -> dict:
        """
        5分钟入场: 快线上穿长周期线金叉, 结合闸门的多均线状态综合打分
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

        # ── 综合打分: 趋势质量(多均线) × 共振新鲜度(双金叉) ──
        aligned = details.get("ma_aligned", False)
        hourly_ago = details.get("hourly_cross_bars_ago")
        hourly_fresh = hourly_ago is not None and hourly_ago <= 4
        min_fresh = cross_ago <= fresh_bars
        price_above = price > latest[fast_col]

        if aligned and hourly_fresh and min_fresh and price_above:
            signal, score = Signal.STRONG_BUY, 98   # 满配共振: 多头排列+双新鲜金叉+价格确认
        elif hourly_fresh and min_fresh and price_above:
            signal, score = Signal.STRONG_BUY, 95   # 双新鲜金叉+价格确认(排列未理顺)
        elif min_fresh and price_above:
            signal, score = Signal.STRONG_BUY, 88   # 5分钟新鲜入场点
        elif min_fresh:
            signal, score = Signal.BUY, 75          # 5分钟新金叉但价格未确认
        else:
            signal, score = Signal.BUY, 62          # 金叉较早, 趋势进行中

        details["hourly_fresh"] = hourly_fresh
        details["min_fresh"] = min_fresh
        return {"signal": signal, "score": score, "details": details}

    # ── 兼容单周期接口 ─────────────────────────────────────

    def evaluate(self, kline: pd.DataFrame, params: dict) -> dict:
        gate = self.evaluate_gate(kline, params)
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

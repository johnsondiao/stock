"""组合策略向量化快速评估 - 全市场一次读入, groupby 按股票批量计算

四段漏斗向量化:
1. 60分钟价格站上快慢线  2. 60分钟金叉  3. 日线MA12>MA60  4. 5分钟金叉

关键: 用 groupby(code).transform 按每只股票独立计算均线与金叉,
不依赖全市场日期对齐（新股/停牌股的缺失日期不会污染其他股票）。
"""

import numpy as np
import pandas as pd

from app.database import get_db
from app.strategy.ma_combo import (
    DEFAULT_HOURLY_FAST, DEFAULT_HOURLY_SLOW,
    DEFAULT_MIN_FAST, DEFAULT_MIN_SLOW,
    DAILY_FAST, DAILY_SLOW,
)
from app.log_config import get_logger

logger = get_logger(__name__)


def _load_long(table: str, codes: list[str] | None = None) -> pd.DataFrame:
    """一次读取 (code, date, close), 按 code+date 排序"""
    with get_db() as conn:
        if codes:
            ph = ",".join("?" * len(codes))
            df = pd.read_sql_query(
                f"SELECT code, date, close FROM {table} WHERE code IN ({ph})",
                conn, params=codes,
            )
        else:
            df = pd.read_sql_query(
                f"SELECT code, date, close FROM {table}", conn
            )
    if df.empty:
        return df
    return df.sort_values(["code", "date"]).reset_index(drop=True)


def _add_ma(df: pd.DataFrame, periods: list[int]) -> pd.DataFrame:
    """按股票分组计算多条均线列 ma{p}"""
    g = df.groupby("code", sort=False)["close"]
    for p in periods:
        df[f"ma{p}"] = g.transform(lambda x, _p=p: x.rolling(_p).mean())
    return df


def _add_cross_ago(df: pd.DataFrame, fast_col: str, slow_col: str, window: int) -> pd.Series:
    """
    每只股票在 window 窗口内最近一次快线上穿慢线距今的K线数
    返回以 code 为索引的 Series, 窗口内无金叉则无该 code
    """
    d = df.copy()
    g = d.groupby("code", sort=False)
    d["prev_fast"] = g[fast_col].shift(1)
    d["prev_slow"] = g[slow_col].shift(1)
    d["rn"] = g.cumcount(ascending=False)          # 0=最新
    d["crossed"] = (d[fast_col] > d[slow_col]) & (d["prev_fast"] <= d["prev_slow"])

    cand = d[d["crossed"] & (d["rn"] < window)]
    if cand.empty:
        return pd.Series(dtype=float)
    ago = cand.groupby("code")["rn"].min()         # 最近一次金叉的距今根数
    return ago.astype(float)


def evaluate_combo_fast(params: dict, candidates: pd.DataFrame) -> dict | None:
    """
    向量化评估组合策略

    :return: {
        "results": [...],        # 完整命中的结果
        "pending_codes": [...],  # 过闸门但缺5分钟/日线缓存的代码（需按需拉取）
        "evaluated": int,
    }; 数据条件不满足时返回 None（调用方回退逐股模式）
    """
    hourly_fast = params.get("hourly_fast", DEFAULT_HOURLY_FAST)
    hourly_slow = params.get("hourly_slow", DEFAULT_HOURLY_SLOW)
    min_fast = params.get("min_fast", DEFAULT_MIN_FAST)
    min_slow = params.get("min_slow", DEFAULT_MIN_SLOW)
    hourly_lookback = params.get("hourly_lookback", 8)
    min_lookback = params.get("min_lookback", 48)
    fresh_bars = params.get("fresh_min_bars", 12)

    cand_set = set(candidates["code"].tolist())

    # ── 阶段1: 60分钟 状态 + 金叉 ──
    h = _load_long("hourly_kline")
    if h.empty:
        return None
    h = h[h["code"].isin(cand_set)]
    if h.empty:
        return None

    h = _add_ma(h, sorted({hourly_fast, hourly_slow}))

    need_rows = hourly_slow + 2
    cnt_h = h.groupby("code")["close"].count()
    h = h[h["code"].isin(cnt_h[cnt_h >= need_rows].index)]
    if h.empty:
        return None

    last = h.groupby("code").tail(1).set_index("code").sort_index()
    price = last["close"]
    fast_v, slow_v = last[f"ma{hourly_fast}"], last[f"ma{hourly_slow}"]

    # A. 价格站上快慢线
    state_ok = (price > fast_v) & (price > slow_v) & fast_v.notna() & slow_v.notna()
    # B. 当前多头 + 金叉在窗口内
    cross_ago_h = _add_cross_ago(h, f"ma{hourly_fast}", f"ma{hourly_slow}", hourly_lookback)
    gate_mask = state_ok & (fast_v > slow_v) & last.index.isin(cross_ago_h.index)

    gate_codes_all = list(last.index[gate_mask])
    logger.info("快速评估: 60分钟闸门通过 %d", len(gate_codes_all))
    if not gate_codes_all:
        return {"results": [], "pending_codes": [], "evaluated": len(cnt_h)}

    # ── 阶段2: 日线趋势确认 MA12 > MA60 ──
    daily = _load_long("daily_kline", gate_codes_all)
    daily_bull = pd.Series(dtype=bool)
    daily_ok_codes: set[str] = set()
    if not daily.empty:
        daily = _add_ma(daily, [DAILY_FAST, DAILY_SLOW])
        cnt_d = daily.groupby("code")["close"].count()
        daily = daily[daily["code"].isin(cnt_d[cnt_d >= DAILY_SLOW + 2].index)]
        if not daily.empty:
            d_last = daily.groupby("code").tail(1).set_index("code")
            d_fast, d_slow = d_last[f"ma{DAILY_FAST}"], d_last[f"ma{DAILY_SLOW}"]
            daily_bull = (d_fast > d_slow) & d_fast.notna() & d_slow.notna()
            daily_ok_codes = set(d_last.index)

    pending_codes: list[str] = []
    gate_codes: list[str] = []
    daily_details: dict[str, tuple[float, float]] = {}
    for c in gate_codes_all:
        if c not in daily_ok_codes:
            pending_codes.append(c)        # 日线缓存缺失/不足 → 按需拉取
        elif bool(daily_bull[c]):
            gate_codes.append(c)
        # 日线未确认 → 直接淘汰

    logger.info("快速评估: 日线趋势确认 %d, 待补日线 %d", len(gate_codes), len(pending_codes))
    if not gate_codes:
        return {"results": [], "pending_codes": pending_codes, "evaluated": len(cnt_h)}

    # ── 阶段3: 5分钟 入场金叉 ──
    m5 = _load_long("kline_5min", gate_codes)
    results: list[dict] = []

    if m5.empty:
        pending_codes.extend(gate_codes)
        return {"results": [], "pending_codes": pending_codes, "evaluated": len(cnt_h)}

    m5 = _add_ma(m5, sorted({min_fast, min_slow}))
    cnt_m = m5.groupby("code")["close"].count()
    ok_codes = set(cnt_m[cnt_m >= min_slow + 2].index)
    for c in gate_codes:
        if c not in ok_codes:
            pending_codes.append(c)        # 5分钟数据不足 → 按需拉取
    m5 = m5[m5["code"].isin(ok_codes)]

    if not m5.empty:
        last5 = m5.groupby("code").tail(1).set_index("code").sort_index()
        price5 = last5["close"]
        cur5 = last5[f"ma{min_fast}"] > last5[f"ma{min_slow}"]
        cross_ago_m = _add_cross_ago(m5, f"ma{min_fast}", f"ma{min_slow}", min_lookback)
        entry_mask = cur5 & last5.index.isin(cross_ago_m.index)
        entry_codes = list(last5.index[entry_mask])

        if entry_codes:
            h_ago = cross_ago_h.reindex(entry_codes)
            m_ago = cross_ago_m.reindex(entry_codes)
            h_fresh = h_ago <= 4
            m_fresh = m_ago <= fresh_bars
            above5 = price5[entry_codes] > last5.loc[entry_codes, f"ma{min_fast}"]

            scores = np.select(
                [
                    (h_fresh & m_fresh & above5).values,
                    (m_fresh & above5).values,
                    m_fresh.values,
                ],
                [98, 90, 75],
                default=62,
            )
            cand_map = candidates.set_index("code")
            for i, code in enumerate(entry_codes):
                score = int(scores[i])
                row = cand_map.loc[code] if code in cand_map.index else None
                results.append({
                    "code": code,
                    "name": str(row["name"]) if row is not None else "",
                    "price": float(row["price"]) if row is not None else float(price5[code]),
                    "pct_change": float(row.get("pct_change", 0)) if row is not None else 0.0,
                    "signal": "strong_buy" if score >= 88 else "buy",
                    "score": score,
                    "hourly_cross_bars_ago": int(h_ago[code]),
                    "min_cross_bars_ago": int(m_ago[code]),
                    "hourly_fresh": bool(h_fresh[code]),
                    "min_fresh": bool(m_fresh[code]),
                    "hourly_ma_fast": round(float(last.loc[code, f"ma{hourly_fast}"]), 4),
                    "hourly_ma_slow": round(float(last.loc[code, f"ma{hourly_slow}"]), 4),
                    "min_ma_fast": round(float(last5.loc[code, f"ma{min_fast}"]), 4),
                    "min_ma_slow": round(float(last5.loc[code, f"ma{min_slow}"]), 4),
                })

    logger.info("快速评估完成: 命中 %d 只, 待补数据 %d 只", len(results), len(pending_codes))
    return {"results": results, "pending_codes": pending_codes, "evaluated": len(cnt_h)}

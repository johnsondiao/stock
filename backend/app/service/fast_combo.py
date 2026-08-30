"""组合策略向量化快速评估 - 全市场一次读入, groupby 按股票批量计算

性能对比:
- 逐股模式: 3000 次 SQL + 3000 次均线计算 ≈ 数分钟
- 向量化模式: 2 次 SQL + groupby 批量计算 ≈ 数秒

关键: 用 groupby(code).transform 按每只股票独立计算均线与金叉,
不依赖全市场日期对齐（新股/停牌股的缺失日期不会污染其他股票）。
"""

import numpy as np
import pandas as pd

from app.database import get_db
from app.strategy.ma_combo import (
    STATE_MA_PERIODS,
    DEFAULT_HOURLY_FAST, DEFAULT_HOURLY_SLOW,
    DEFAULT_MIN_FAST, DEFAULT_MIN_SLOW,
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
    返回以 code 为索引的 Series, 窗口内无金叉为 NaN
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
        "pending_codes": [...],  # 过了60分钟闸门但缺5分钟缓存的代码（需按需拉取）
        "evaluated": int,
    }; 数据条件不满足时返回 None（调用方回退逐股模式）
    """
    min_above = params.get("min_above", 4)
    hourly_fast = params.get("hourly_fast", DEFAULT_HOURLY_FAST)
    hourly_slow = params.get("hourly_slow", DEFAULT_HOURLY_SLOW)
    min_fast = params.get("min_fast", DEFAULT_MIN_FAST)
    min_slow = params.get("min_slow", DEFAULT_MIN_SLOW)
    hourly_lookback = params.get("hourly_lookback", 8)
    min_lookback = params.get("min_lookback", 48)
    fresh_bars = params.get("fresh_min_bars", 12)

    cand_set = set(candidates["code"].tolist())

    # ── 阶段1: 60分钟 全市场批量评估 ──
    h = _load_long("hourly_kline")
    if h.empty:
        return None
    h = h[h["code"].isin(cand_set)]
    if h.empty:
        return None

    periods = sorted(set(STATE_MA_PERIODS + [hourly_fast, hourly_slow]))
    h = _add_ma(h, periods)

    # 每只股票数据量过滤（新股历史短）
    need_rows = max(hourly_slow, max(STATE_MA_PERIODS)) + 2
    cnt_h = h.groupby("code")["close"].count()
    valid_codes = cnt_h[cnt_h >= need_rows].index
    h = h[h["code"].isin(valid_codes)]
    if h.empty:
        return None

    # 每只股票最后一根（最新）
    last = h.groupby("code").tail(1).set_index("code").sort_index()
    price = last["close"]

    # 站上均线数量（NaN → 不计入）
    above = pd.Series(0, index=last.index)
    for p in STATE_MA_PERIODS:
        above = above + (price > last[f"ma{p}"]).astype(int)

    # 均线多头排列
    vals = [last[f"ma{p}"] for p in STATE_MA_PERIODS]
    aligned = pd.Series(True, index=last.index)
    for i in range(len(vals) - 1):
        aligned &= vals[i].notna() & vals[i + 1].notna() & (vals[i] >= vals[i + 1])

    cur_bull = last[f"ma{hourly_fast}"] > last[f"ma{hourly_slow}"]
    cross_ago_h = _add_cross_ago(h, f"ma{hourly_fast}", f"ma{hourly_slow}", hourly_lookback)

    gate_mask = (above >= min_above) & cur_bull & last.index.isin(cross_ago_h.index)
    gate_codes = list(last.index[gate_mask])
    logger.info("快速评估: 60分钟闸门通过 %d/%d", len(gate_codes), len(valid_codes))

    if not gate_codes:
        return {"results": [], "pending_codes": [], "evaluated": len(valid_codes)}

    # ── 阶段2: 5分钟 仅对闸门通过者批量评估 ──
    m5 = _load_long("kline_5min", gate_codes)
    results: list[dict] = []
    pending_codes: list[str] = []

    if m5.empty:
        return {"results": [], "pending_codes": gate_codes, "evaluated": len(valid_codes)}

    m5 = _add_ma(m5, sorted({min_fast, min_slow}))
    cnt_m = m5.groupby("code")["close"].count()
    ok_codes = cnt_m[cnt_m >= min_slow + 2].index
    for c in gate_codes:
        if c not in set(ok_codes):
            pending_codes.append(c)          # 数据不足 → 按需拉取
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
            al = aligned.reindex(entry_codes)

            scores = np.select(
                [
                    (al & h_fresh & m_fresh & above5).values,
                    (h_fresh & m_fresh & above5).values,
                    (m_fresh & above5).values,
                    m_fresh.values,
                ],
                [98, 95, 88, 75],
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
                    "above_count": int(above[code]),
                    "total_ma": len(STATE_MA_PERIODS),
                    "ma_aligned": bool(al[code]),
                    "hourly_cross_bars_ago": int(h_ago[code]),
                    "min_cross_bars_ago": int(m_ago[code]),
                    "hourly_fresh": bool(h_fresh[code]),
                    "min_fresh": bool(m_fresh[code]),
                    "hourly_ma_fast": round(float(last.loc[code, f"ma{hourly_fast}"]), 4),
                    "hourly_ma_slow": round(float(last.loc[code, f"ma{hourly_slow}"]), 4),
                    "min_ma_fast": round(float(last5.loc[code, f"ma{min_fast}"]), 4),
                    "min_ma_slow": round(float(last5.loc[code, f"ma{min_slow}"]), 4),
                })

    logger.info("快速评估完成: 命中 %d 只, 待补5分钟数据 %d 只", len(results), len(pending_codes))
    return {"results": results, "pending_codes": pending_codes, "evaluated": len(valid_codes)}

# -*- coding: utf-8 -*-
"""
ma_combo 策略严格回测
======================
完全复用 backend/app/strategy/ma_combo.py 的四段漏斗逻辑:
  1. 60分钟: 现价>MA24 且 >MA60, 且 MA24 上穿 MA60 金叉在最近 8 根(2交易日)内
  2. 日线:   MA12 > MA60 (趋势确认)
  3. 5分钟:  MA12 上穿 MA288 金叉在最近 48 根(1交易日)内  -> 真正扣扳机
出场纪律: 收盘跌破日线 MA12, 次日开盘卖出

数据约束(已实测):
  daily_kline 全市场覆盖 2025-06-20 起
  hourly_kline 全市场覆盖 2026-05-28 起
  kline_5min  全市场覆盖 2026-08-26 起  (新浪分钟线只给约2周历史)
=> 严格回测窗口被 5min 卡在 2026-08-26 ~ 2026-09-11 (13交易日),
   有效信号日约 9/05 之后(5min MA288 需~10天预热)

成交价: 信号次日开盘买, 出场次日开盘卖 (无未来函数)
费率: 买入万3 + 卖出万3 + 印花税万5 = 单边约万3/万8
"""
import sqlite3, numpy as np, pandas as pd, io, time
from datetime import datetime

DB = r"d:\vibecoding\stock\backend\data\stock.db"
OUT = r"d:\vibecoding\stock\ma_combo_backtest.txt"

# ---- 与 ma_combo.py 默认参数一致 ----
HOURLY_FAST, HOURLY_SLOW = 24, 60
MIN_FAST, MIN_SLOW = 12, 288
HOURLY_LOOKBACK = 8      # 60min金叉窗口(根) = 2交易日
MIN_LOOKBACK = 48        # 5min 金叉窗口(根) = 1交易日
FRESH_MIN_BARS = 12
DAILY_FAST, DAILY_SLOW = 12, 60
BUY_FEE, SELL_FEE = 0.0003, 0.0008

L = []
def P(s=""):
    L.append(str(s)); print(s)

# ---- 向量化金叉距离: 每个bar距最近一次 fast上穿slow 的根数 ----
def vec_cross_ago(fast, slow, max_look=400):
    fast = np.asarray(fast, float); slow = np.asarray(slow, float)
    n = len(fast)
    diff = fast - slow
    prev = np.concatenate([[np.nan], diff[:-1]])   # shift(1), 首帧 nan
    cross = (diff > 0) & (prev <= 0)
    idx = np.where(cross)[0]
    if len(idx) == 0:
        return np.full(n, np.nan)
    pos = np.searchsorted(idx, np.arange(n), side="right") - 1
    pos = np.clip(pos, 0, len(idx) - 1)
    cao = (np.arange(n) - idx[pos]).astype(float)
    cao[np.arange(n) < idx[0]] = np.nan              # 首根金叉之前 = 无金叉
    cao = np.where(cao > max_look, np.nan, cao)
    return cao

def day(s):
    return s[:10] if isinstance(s, str) else str(s)[:10]

# ---- 逐股票计算三套指标 + 每日收盘快照 + 信号日 ----
def process(code, d_df, h_df, m_df):
    if d_df is None or len(d_df) < DAILY_SLOW + 2:
        return None
    d = d_df.sort_values("date").reset_index(drop=True)
    d_close = d["close"].astype(float).values
    d_open = d["open"].astype(float).values
    d_dates = [day(x) for x in d["date"]]
    d_ma12 = pd.Series(d_close).rolling(DAILY_FAST).mean().values
    d_ma60 = pd.Series(d_close).rolling(DAILY_SLOW).mean().values

    # 60min: 每日最后一根(15:00)
    h = h_df.sort_values("date").reset_index(drop=True) if h_df is not None else None
    h_map = {}
    if h is not None and len(h) >= HOURLY_SLOW + 2:
        hc = h["close"].astype(float).values
        hma24 = pd.Series(hc).rolling(HOURLY_FAST).mean().values
        hma60 = pd.Series(hc).rolling(HOURLY_SLOW).mean().values
        hcao = vec_cross_ago(hma24, hma60, max_look=200)
        hs = pd.DataFrame({"d": [day(x) for x in h["date"]], "ma24": hma24,
                           "ma60": hma60, "cao": hcao})
        hs = hs.groupby("d").last()
        h_map = {r: (hs.loc[r, "ma24"], hs.loc[r, "ma60"], hs.loc[r, "cao"])
                 for r in hs.index}

    # 5min: 每日最后一根(15:00)
    m = m_df.sort_values("date").reset_index(drop=True) if m_df is not None else None
    m_map = {}
    if m is not None and len(m) >= MIN_SLOW + 2:
        mc = m["close"].astype(float).values
        mma12 = pd.Series(mc).rolling(MIN_FAST).mean().values
        mma288 = pd.Series(mc).rolling(MIN_SLOW).mean().values
        mcao = vec_cross_ago(mma12, mma288, max_look=400)
        ms = pd.DataFrame({"d": [day(x) for x in m["date"]], "ma12": mma12,
                           "ma288": mma288, "cao": mcao})
        ms = ms.groupby("d").last()
        m_map = {r: (ms.loc[r, "ma12"], ms.loc[r, "ma288"], ms.loc[r, "cao"])
                 for r in ms.index}

    sig = {}   # date -> score
    for i, dt in enumerate(d_dates):
        if dt not in h_map or dt not in m_map:
            continue
        if not np.isfinite(d_ma12[i]) or not np.isfinite(d_ma60[i]):
            continue
        price = d_close[i]
        h24, h60, hcao = h_map[dt]
        m12, m288, mcao = m_map[dt]
        # 闸门 A: 价格站上60min快慢线
        if pd.isna(h24) or pd.isna(h60) or not (price > h24 and price > h60):
            continue
        # 闸门 B: 60min金叉且新鲜
        if h24 <= h60:
            continue
        if pd.isna(hcao) or hcao >= HOURLY_LOOKBACK:
            continue
        # 闸门 C: 日线趋势
        if d_ma12[i] <= d_ma60[i]:
            continue
        # 入场: 5min金叉
        if pd.isna(m12) or pd.isna(m288) or m12 <= m288:
            continue
        if pd.isna(mcao) or mcao >= MIN_LOOKBACK:
            continue
        hourly_fresh = (hcao is not None) and (hcao <= 4)
        min_fresh = (mcao is not None) and (mcao <= FRESH_MIN_BARS)
        price_above = price > m12
        if hourly_fresh and min_fresh and price_above:
            score = 98
        elif min_fresh and price_above:
            score = 90
        elif min_fresh:
            score = 75
        else:
            score = 62
        sig[dt] = score

    return {
        "dates": d_dates, "open": d_open, "close": d_close,
        "ma12": d_ma12, "ma60": d_ma60, "sig": sig,
    }

def main():
    t0 = time.time()
    P(f"加载数据 {datetime.now():%H:%M:%S}")
    db = sqlite3.connect(DB, timeout=120)
    daily = pd.read_sql_query(
        "SELECT code,date,open,high,low,close FROM daily_kline WHERE date>='2025-01-01'",
        db)
    hourly = pd.read_sql_query(
        "SELECT code,date,open,high,low,close FROM hourly_kline WHERE date>='2026-01-01'",
        db)
    kmin = pd.read_sql_query(
        "SELECT code,date,open,high,low,close FROM kline_5min WHERE date>='2026-07-01'",
        db)
    db.close()
    P(f"  daily={len(daily)} hourly={len(hourly)} kmin={len(kmin)}  "
      f"({time.time()-t0:.1f}s)")

    def group(df):
        g = {}
        for c, sub in df.groupby("code"):
            g[c] = sub
        return g
    gd, gh, gm = group(daily), group(hourly), group(kmin)
    codes = sorted(set(gd) & set(gh) & set(gm))
    # 窗口: 5min 全市场覆盖起点(每天≥2000只的最早日)
    km = kmin.copy(); km["d"] = km["date"].str[:10]
    cnt = km.groupby("d").size()
    full = cnt[cnt >= 2000]
    window_start = full.index[0] if len(full) else sorted(cnt.index)[0]
    P(f"股票数={len(codes)}  回测窗口起点(5min全市场覆盖)={window_start}")

    # ---- 全市场等权日收益(基准) ----
    close_piv = daily.pivot_table(index="date", columns="code",
                                  values="close", aggfunc="last").sort_index()
    close_piv.index = [day(x) for x in close_piv.index]
    mkt_ret = close_piv.pct_change().median(axis=1)        # 每日全市场中位数收益
    mkt_idx = list(mkt_ret.index)
    def mkt_between(b, s):
        if b not in mkt_idx or s not in mkt_idx:
            return np.nan
        i, j = mkt_idx.index(b), mkt_idx.index(s)
        return float(mkt_ret.iloc[i:j + 1].sum() * 100)    # 持有期市场收益(%)

    arr = {}
    sig_by_date = {}
    n_sig = 0
    for c in codes:
        r = process(c, gd.get(c), gh.get(c), gm.get(c))
        if r is None:
            continue
        arr[c] = r
        for dt, sc in r["sig"].items():
            if dt < window_start:
                continue
            sig_by_date.setdefault(dt, []).append((c, sc))
            n_sig += 1
    P(f"信号总数={n_sig}  信号日数={len(sig_by_date)}")

    # ---- 逐股票独立交易模拟(信号级, 不跨股竞争资金) ----
    trades = []
    for c, r in arr.items():
        dates, op, cl = r["dates"], r["open"], r["close"]
        ma12 = r["ma12"]
        n = len(dates)
        holding = None  # (buy_px, buy_date, buy_idx, score)
        for j in range(n):
            dt = dates[j]
            if dt < window_start:
                continue
            # 出场: 持有中 且 今日收盘<MA12 -> 次日开盘卖
            if holding is not None:
                if j + 1 < n and cl[j] < ma12[j]:
                    sell_px = op[j + 1]
                    ret = (sell_px / holding[0] - 1) * 100 - (BUY_FEE + SELL_FEE) * 100
                    trades.append((c, holding[1], dates[j + 1], ret,
                                   j + 1 - holding[2], holding[3]))
                    holding = None
            # 入场: 今日有信号 且 未持有 -> 次日开盘买
            if dt in r["sig"] and holding is None:
                if j + 1 < n:
                    holding = (op[j + 1], dates[j + 1], j + 1, r["sig"][dt])
        # 末尾未平仓: 按最后一日开盘平(保守)
        if holding is not None:
            ret = (op[-1] / holding[0] - 1) * 100 - (BUY_FEE + SELL_FEE) * 100
            trades.append((c, holding[1], dates[-1] + "(末平)", ret,
                           n - 1 - holding[2], holding[3]))

    P(f"完成交易模拟: {len(trades)} 笔  ({time.time()-t0:.1f}s)")

    # ---- 汇总 ----
    if trades:
        tr = np.array([t[3] for t in trades], dtype=float)
        dd = np.array([t[4] for t in trades], dtype=float)
        sc = np.array([t[5] for t in trades], dtype=float)
        win = (tr > 0).mean() * 100
        P("")
        P("=" * 88)
        P("ma_combo 严格回测结果 (窗口 2026-08-26~2026-09-11, 真实分钟线)")
        P("=" * 88)
        P(f"交易笔数        : {len(tr)}")
        P(f"胜率            : {win:.1f}%")
        P(f"平均收益/笔     : {tr.mean():+.2f}%   中位: {np.median(tr):+.2f}%")
        P(f"平均持有        : {dd.mean():.1f} 交易日   中位: {np.median(dd):.0f}")
        P(f"最佳/最差       : {tr.max():+.2f}% / {tr.min():+.2f}%")
        # 收益分布
        P("")
        P("收益分布:")
        bins = [(-1e9, -5), (-5, -2), (-2, 0), (0, 2), (2, 5), (5, 1e9)]
        for lo, hi in bins:
            cnt = int(((tr >= lo) & (tr < hi)).sum())
            lab = f"[{lo:+.0f},{hi:+.0f})" if hi < 1e9 else f"[>{lo:+.0f}"
            P(f"  {lab:<14} {cnt:>4} 笔  ({cnt/len(tr)*100:4.1f}%)")
        # 按评分分组
        P("")
        P("按信号评分分组:")
        for sval in sorted(set(sc)):
            m = sc == sval
            P(f"  评分={int(sval):>3}: {int(m.sum()):>3} 笔  平均 {tr[m].mean():+6.2f}%  "
              f"胜率 {(tr[m]>0).mean()*100:4.1f}%")
        # 逐笔明细
        P("")
        P("逐笔明细 (买入日 代码 卖出日 收益% 持有天 评分):")
        for c, bdt, sdt, ret, hd, sval in sorted(trades, key=lambda x: x[1]):
            P(f"  {bdt}  {c}  ->  {sdt:<16} {ret:+6.2f}%  {hd:>3.0f}天  {int(sval)}")

        # ---- 市场基准对照 ----
        P("")
        P("-" * 88)
        P("对照: 每笔交易同期『全市场等权买入持有』收益")
        beat = 0; mkt_all = []
        for c, bdt, sdt, ret, hd, sval in trades:
            sd = sdt.replace("(末平)", "")
            mb = mkt_between(bdt, sd)
            if not np.isnan(mb):
                mkt_all.append(mb)
                if ret > mb:
                    beat += 1
        if mkt_all:
            ma = np.array(mkt_all)
            P(f"  策略平均      : {tr.mean():+.2f}%")
            P(f"  市场基准平均  : {ma.mean():+.2f}%   (持有期等长等权)")
            P(f"  策略跑赢市场  : {beat}/{len(ma)} 笔 ({beat/len(ma)*100:.0f}%)")
            P(f"  超额(策略-市场): {tr.mean()-ma.mean():+.2f} 个百分点/笔")
            # 区间市场涨跌
            seg = mkt_ret[(mkt_ret.index >= window_start)]
            P(f"  窗口内全市场累计中位收益: {seg.sum()*100:+.2f}%  "
              f"(单日中位均值 {seg.mean()*100:+.2f}%)")
    else:
        P("窗口内无成交 (样本不足)")

    io.open(OUT, "w", encoding="utf-8").write("\n".join(L))
    P(f"\n输出: {OUT}")

if __name__ == "__main__":
    main()

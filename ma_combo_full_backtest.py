# -*- coding: utf-8 -*-
"""
ma_combo 完整版回测(三道闸门) + 真实资金组合模拟
==================================================
在 ma_combo_backtest.py 的基础上:
1. 逐股票信号复用 ma_combo.py 四段漏斗(60min/日线/5min)
2. 新增两道闸门(与线上一致):
   - 市场广度门限: 信号日全市场上涨占比 >=50% 才允许入场
   - 板块成色: 板块5日中位涨幅>0 且 离散度排进最齐前30%
3. 组合级资金模拟: 初始1万元, 单票最多15%, 整手(100股),
   信号次日开盘买, 收盘破MA12次日开盘卖, 含手续费

对比三个版本: A 原策略 / B +广度门限 / C +广度+板块(当前线上版)
窗口受5min数据限制: 2026-08-26 ~ 2026-09-11
"""
import io
import sqlite3
import time
from datetime import datetime

import numpy as np
import pandas as pd

from ma_combo_backtest import process, vec_cross_ago  # 复用信号计算

DB = r"d:\vibecoding\stock\backend\data\stock.db"
IND = r"d:\vibecoding\stock\industry_map.csv"
OUT = r"d:\vibecoding\stock\ma_combo_full_backtest.txt"

BUY_FEE, SELL_FEE = 0.0003, 0.0008
CAPITAL = 10000.0
MAX_POS_PCT = 0.15          # 单票最多总资产15%
LOT = 100                   # 整手
BREADTH_GATE = 50.0
DISP_PCT = 0.30
MIN_SECTOR = 5

L = []
def P(s=""):
    L.append(str(s)); print(s)


def load_data():
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
    return daily, hourly, kmin


def sector_stats_by_date(px, imap, dates, lookback=5):
    """每个交易日计算板块成色: {date: {sector: (ret5_median, disp_rank)}}"""
    out = {}
    members = pd.Series(imap)
    members = members[members.index.isin(px.columns)]
    sectors = members.unique()
    ret = px.pct_change(lookback) * 100          # 每股5日涨幅
    for dt in dates:
        if dt not in ret.index:
            continue
        r = ret.loc[dt]
        st = {}
        for s in sectors:
            cs = members[members == s].index
            v = r.loc[cs].dropna()
            if len(v) < MIN_SECTOR:
                continue
            st[s] = (float(v.median()), float(v.std()))
        if not st:
            continue
        df = pd.DataFrame(st, index=["ret5", "disp"]).T
        rk = df["disp"].rank(method="average")
        n = len(df)
        df["disp_rank"] = (rk - 1) / (n - 1) if n > 1 else 1.0
        out[dt] = df
    return out


def simulate(trades_by_date, px_open, px_close, dates, arr, gates, label):
    """
    组合级模拟。trades_by_date: {signal_date: [(code, score)]}
    gates: dict(breadth=dict(date->bool), sector=dict((code,date)->bool))
    """
    cash = CAPITAL
    holdings = {}     # code -> (lots, buy_px, buy_date)
    last_px = {}      # code -> 最近已知收盘价(停牌时用买入价/最后价)
    equity_curve = []
    trade_log = []
    n_blocked_b, n_blocked_s = 0, 0
    dbg = []          # 调试日志

    def mark(c):
        """股票 c 的当前估值价"""
        return last_px.get(c, holdings.get(c, (0, 0, ""))[1])

    for k, dt in enumerate(dates):
        if k == 0:
            continue
        prev = dates[k - 1]
        # ---- 1) 出场: 昨日收盘破MA12 -> 今日开盘卖 ----
        for c in list(holdings):
            r = arr[c]
            i = r["dates"].index(prev) if prev in r["dates"] else None
            if i is None:
                continue
            if r["close"][i] < r["ma12"][i] and dt in px_open.index \
                    and c in px_open.columns and np.isfinite(px_open.loc[dt, c]):
                lots, bpx, bdt = holdings.pop(c)
                spx = px_open.loc[dt, c]
                cash += lots * LOT * spx * (1 - SELL_FEE)
                ret = (spx / bpx - 1) * 100 - (BUY_FEE + SELL_FEE) * 100
                trade_log.append((c, bdt, dt, ret, lots, bpx, spx))
        # ---- 2) 入场: 昨日信号 -> 今日开盘买 ----
        cands = []
        for c, score in trades_by_date.get(prev, []):
            if c in holdings:
                continue
            if gates is not None:
                # 注意: breadth_gate 的值可能是 numpy.bool_, 不能用 `is False` 判断
                if gates["breadth"].get(prev) is not None and \
                        not gates["breadth"][prev]:
                    n_blocked_b += 1
                    continue
                if gates["sector"] is not None and \
                        gates["sector"].get((c, prev)) is False:
                    n_blocked_s += 1
                    continue
            cands.append((score, c))
            cands.sort(reverse=True)
        for score, c in cands:
            if dt not in px_open.index or c not in px_open.columns:
                continue
            bpx = px_open.loc[dt, c]
            if not np.isfinite(bpx) or bpx <= 0:
                continue
            equity_now = cash + sum(lts * LOT * mark(cc)
                                    for cc, (lts, _, _) in holdings.items())
            alloc = min(equity_now * MAX_POS_PCT, cash)
            lots = int(alloc / (bpx * LOT))
            if lots < 1:
                continue
            cost = lots * bpx * LOT * (1 + BUY_FEE)
            if cost > cash:
                continue
            cash -= cost
            holdings[c] = (lots, bpx, dt)
            last_px[c] = bpx
            dbg.append(f"{dt} BUY {c} lots={lots} px={bpx:.2f} cost={cost:.0f} cash={cash:.0f}")
        # ---- 3) 更新最新价并记录当日市值 ----
        if dt in px_close.index:
            row = px_close.loc[dt]
            for c in list(holdings):
                if c in row.index and np.isfinite(row[c]) and row[c] > 0:
                    last_px[c] = row[c]
            mv = sum(lts * LOT * mark(c) for c, (lts, _, _) in holdings.items())
            equity_curve.append((dt, cash + mv))
            if holdings:
                dbg.append(f"{dt} EOD cash={cash:.0f} mv={mv:.0f} eq={cash+mv:.0f} " +
                           ",".join(f"{c}:{mark(c):.2f}x{lts*LOT}" for c, (lts, _, _) in holdings.items()))
    # 末尾未平仓按最后已知价计
    final = cash + sum(lts * LOT * mark(c) for c, (lts, _, _) in holdings.items())
    open_pos = list(holdings)

    eq = pd.Series([e for _, e in equity_curve],
                   index=[d for d, _ in equity_curve])
    peak = eq.cummax()
    mdd = float((eq / peak - 1).min() * 100) if len(eq) else 0.0

    P("")
    P("=" * 78)
    P(f"{label}")
    P("=" * 78)
    P(f"初始资金      : {CAPITAL:,.0f} 元")
    P(f"期末资产      : {final:,.0f} 元  ({(final/CAPITAL-1)*100:+.2f}%)")
    P(f"盈亏金额      : {final-CAPITAL:+,.0f} 元")
    P(f"最大回撤      : {mdd:+.2f}%")
    P(f"完成交易      : {len(trade_log)} 笔  胜率 "
      f"{(np.mean([t[3]>0 for t in trade_log])*100 if trade_log else 0):.0f}%  "
      f"平均 {np.mean([t[3] for t in trade_log]) if trade_log else 0:+.2f}%/笔")
    if gates is not None:
        P(f"被广度门限拦下: {n_blocked_b} 笔   被板块成色拦下: {n_blocked_s} 笔")
    if trade_log:
        P("逐笔: 股票 买入日 卖出日 收益% 股数 买价 卖价")
        for c, bdt, sdt, ret, lots, bpx, spx in sorted(trade_log, key=lambda x: x[1]):
            P(f"  {c} {bdt} -> {sdt}  {ret:+6.2f}%  {lots*LOT:>5}股"
              f"  {bpx:.2f} -> {spx:.2f}")
    P("调试流水:")
    for d in dbg:
        P("  " + d)
    if open_pos:
        last = dates[-1]
        P(f"期末持仓(按最近已知价计): " + ", ".join(
            f"{c}x{lts * LOT}" for c in open_pos
            for lts in [holdings[c][0]]))
    if len(eq):
        P("每日资产: " + " ".join(f"{d[-5:]}={v:,.0f}" for d, v in equity_curve))
    return final


def main():
    t0 = time.time()
    P(f"加载数据 {datetime.now():%H:%M:%S}")
    daily, hourly, kmin = load_data()
    P(f"  daily={len(daily)} hourly={len(hourly)} kmin={len(kmin)}")

    gd = {c: g for c, g in daily.groupby("code")}
    gh = {c: g for c, g in hourly.groupby("code")}
    gm = {c: g for c, g in kmin.groupby("code")}
    codes = sorted(set(gd) & set(gh) & set(gm))

    km = kmin.copy(); km["d"] = km["date"].str[:10]
    cnt = km.groupby("d").size()
    full = cnt[cnt >= 2000]
    window_start = full.index[0]
    # 截止到最后一个已收盘日(排除盘中当日)
    today = datetime.now().strftime("%Y-%m-%d")
    all_dates = sorted({d[:10] for d in daily["date"]})
    window = [d for d in all_dates if window_start <= d < today]
    P(f"股票数={len(codes)}  窗口 {window[0]} ~ {window[-1]} ({len(window)}交易日)")

    # ---- 每日广度(信号日口径: 当天全市场上涨占比) ----
    close_piv = daily.pivot_table(index="date", columns="code",
                                  values="close", aggfunc="last").sort_index()
    close_piv.index = [d[:10] for d in close_piv.index]
    breadth = ((close_piv.pct_change() > 0).mean(axis=1) * 100)
    breadth_gate = {d: (breadth.get(d, 0) >= BREADTH_GATE) for d in window}
    P("广度: " + " ".join(
        f"{d[-5:]}={breadth.get(d, 0):.0f}%{'√' if breadth_gate[d] else '×'}"
        for d in window))

    # ---- 板块成色(每日) ----
    imap = dict(zip(pd.read_csv(IND, encoding="utf-8-sig", dtype=str)["code"],
                    pd.read_csv(IND, encoding="utf-8-sig", dtype=str)["sector"]))
    sec_stats = sector_stats_by_date(close_piv, imap, window)

    # ---- 逐股票信号 ----
    arr = {}
    sig_by_date = {}
    for c in codes:
        r = process(c, gd.get(c), gh.get(c), gm.get(c))
        if r is None:
            continue
        arr[c] = r
        for dt, sc in r["sig"].items():
            if dt in window:
                sig_by_date.setdefault(dt, []).append((c, sc))
    n_sig = sum(len(v) for v in sig_by_date.values())
    P(f"信号总数={n_sig}  信号日数={len(sig_by_date)}  ({time.time()-t0:.0f}s)")

    # 板块闸门判定: (code, date) -> 是否放行(映射缺失放行)
    sector_gate = {}
    for dt, lst in sig_by_date.items():
        st = sec_stats.get(dt)
        for c, _ in lst:
            s = imap.get(c)
            if st is None or s is None or s not in st.index:
                sector_gate[(c, dt)] = True      # 缺数据不误杀
            else:
                row = st.loc[s]
                sector_gate[(c, dt)] = bool(row["ret5"] > 0
                                            and row["disp_rank"] <= DISP_PCT)

    # 开盘价矩阵
    open_piv = daily.pivot_table(index="date", columns="code",
                                 values="open", aggfunc="last").sort_index()
    open_piv.index = [d[:10] for d in open_piv.index]

    # ---- 三版本对比 ----
    simulate(sig_by_date, open_piv, close_piv, window, arr, None,
             "A 原 ma_combo (无闸门)")
    simulate(sig_by_date, open_piv, close_piv, window, arr,
             {"breadth": breadth_gate, "sector": None},
             "B ma_combo + 广度门限(50%)")
    simulate(sig_by_date, open_piv, close_piv, window, arr,
             {"breadth": breadth_gate, "sector": sector_gate},
             "C ma_combo + 广度门限 + 板块成色 (当前线上版)")

    io.open(OUT, "w", encoding="utf-8").write("\n".join(L))
    P(f"\n输出: {OUT}")


if __name__ == "__main__":
    main()

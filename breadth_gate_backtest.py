# -*- coding: utf-8 -*-
"""
广度门限回测: "只有市场广度健康时才买入"能否提升均线入场收益?
入场与止损规则与 stop_loss_backtest.py 的规则A一致(上穿MA12且MA12>MA60,
次日开盘买; 收盘破MA12次日开盘卖), 按入场日广度分组对比。
"""
import sqlite3
import numpy as np
import pandas as pd

DB = r"d:\vibecoding\stock\backend\data\stock.db"
OUT = r"d:\vibecoding\stock\breadth_gate_backtest.txt"
BUY_FEE = SELL_FEE = 0.0003

lines = []
P = lines.append

db = sqlite3.connect(DB, timeout=60)
df = pd.read_sql_query(
    "SELECT code, substr(date,1,10) d, open, close FROM daily_kline "
    "WHERE date>='2025-01-01'", db)
db.close()

px_c = df.pivot_table(index="d", columns="code", values="close", aggfunc="last").sort_index()
px_o = df.pivot_table(index="d", columns="code", values="open", aggfunc="last").sort_index()
# 只用全市场覆盖的完整交易日
full_days = px_c.index[px_c.notna().sum(axis=1) >= 2000]
px_c = px_c.loc[full_days]
px_o = px_o.loc[full_days]

# 广度 = 当天上涨个股占比
chg = px_c.pct_change()
breadth = (chg > 0).mean(axis=1) * 100
P(f"交易日 {len(full_days)} 个 ({full_days[0]} ~ {full_days[-1]})")

trades = []  # (code, entry_day, breadth_at_signal, ret, hold_days)
codes = list(px_c.columns)
for c in codes:
    s = px_c[c].values.astype(float)
    o = px_o[c].values.astype(float)
    if len(s) < 70 or np.isnan(s).any():
        continue
    ma12 = pd.Series(s).rolling(12).mean().values
    ma60 = pd.Series(s).rolling(60).mean().values
    n = len(s)
    holding = None
    for i in range(60, n - 1):
        sig = (s[i-1] <= ma12[i-1]) and (s[i] > ma12[i]) and (ma12[i] > ma60[i])
        if holding is None and sig and np.isfinite(o[i+1]) and o[i+1] > 0:
            holding = (o[i+1], i+1)
        elif holding is not None:
            if s[i] < ma12[i] and np.isfinite(o[i+1]) and o[i+1] > 0:
                ret = (o[i+1]/holding[0]-1)*100 - (BUY_FEE+SELL_FEE)*100
                trades.append((c, full_days[holding[1]], breadth.iloc[holding[1]-1], ret, i+1-holding[1]))
                holding = None
    if holding is not None:
        valid = s[np.isfinite(s) & (s > 0)]
        if len(valid) and holding[0] > 0:
            ret = (valid[-1]/holding[0]-1)*100 - (BUY_FEE+SELL_FEE)*100
            trades.append((c, full_days[holding[1]], breadth.iloc[holding[1]-1], ret, n-holding[1]))

T = pd.DataFrame(trades, columns=["code", "entry", "breadth", "ret", "hold"])
P(f"总交易 {len(T)} 笔")
P("")

P("=" * 92)
P("按 买入日市场广度 分组 (广度=当天上涨个股占比, 信号日口径)")
P("=" * 92)
bins = [(0, 35), (35, 50), (50, 65), (65, 101)]
P(f"{'广度区间':<12}{'笔数':>7}{'平均收益':>10}{'中位':>9}{'胜率':>8}{'亏超5%':>9}{'持有天':>8}")
for lo, hi in bins:
    g = T[(T["breadth"] >= lo) & (T["breadth"] < hi)]
    if not len(g):
        continue
    P(f"[{lo:>3},{hi:>3}){'':<4}{len(g):>7}{g['ret'].mean():>+9.2f}%"
      f"{g['ret'].median():>+8.2f}%{(g['ret']>0).mean()*100:>7.1f}%"
      f"{(g['ret']<-5).mean()*100:>8.1f}%{g['hold'].mean():>7.1f}")

# 用信号日(而非买入日)前一天广度也试一遍 —— 实操中尾盘决策用的是当日盘中广度
P("")
gate = 50.0
for gate in [35, 50]:
    keep = T[T["breadth"] >= gate]
    drop = T[T["breadth"] < gate]
    P(f"门限 广度>={gate}%: 保留 {len(keep)} 笔 平均 {keep['ret'].mean():+.2f}% 胜率 {(keep['ret']>0).mean()*100:.1f}%"
      f"   |   拦下 {len(drop)} 笔 平均 {drop['ret'].mean():+.2f}% 胜率 {(drop['ret']>0).mean()*100:.1f}%")

P("")
P("=" * 92)
P("对照: 三峡水利买入日(2026-09-09)的广度 = 37.4%")
P("=" * 92)

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("\n".join(lines))

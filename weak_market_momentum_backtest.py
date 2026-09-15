# -*- coding: utf-8 -*-
"""
问题: 弱市(广度<50%)里, 买当天唯一在涨的股票, 能不能赚钱?

验证框架(不预测, 只做事后统计):
- 事件: 弱市交易日, 个股当日上涨(逆势)
- 买入: 次日开盘
- 持有: 5 个交易日后收盘卖
- 对照: ① 同期全市场等权 ② 强市日买入的同类股票
- 分组: 按逆势涨幅分档(温和/强势/暴涨), 另测"连续多日逆势"
- 样本外: 按时间对半分, 前半训练观察, 后半验证
"""
import sqlite3
import numpy as np
import pandas as pd

DB = r"D:\vibecoding\stock\backend\data\stock.db"
OUT = r"D:\vibecoding\stock\weak_market_momentum_backtest.txt"
FEE = 0.0008          # 双边合计约万16(含佣金卖印花)
HOLD = 5              # 持有交易日
WEAK = 50.0           # 广度阈值 %

lines = []
P = lines.append
db = sqlite3.connect(DB, timeout=60)

# ---- 数据: 日线全市场(2025-06-20 起全覆盖) ----
df = pd.read_sql_query(
    "SELECT substr(date,1,10) d, code, open, close FROM daily_kline "
    "WHERE date>='2025-06-20' ORDER BY date", db)
db.close()

op = df.pivot_table(index="d", columns="code", values="open", aggfunc="first").sort_index()
cl = df.pivot_table(index="d", columns="code", values="close", aggfunc="last").sort_index()
chg = cl.pct_change() * 100
valid = cl.notna() & (cl > 0)

# ---- 每日广度 ----
breadth = (chg > 0).sum(axis=1) / chg.notna().sum(axis=1) * 100
mkt_ret = chg.median(axis=1)                      # 当日等权中位

dates = cl.index.tolist()
n = len(dates)
P("=" * 92)
P("回测: 弱市里买'唯一在涨的股票'能不能赚钱")
P("=" * 92)
P(f"样本区间: {dates[0]} ~ {dates[-1]}   共 {n} 个交易日")
weak_days = [d for d in dates if breadth.get(d, 100) < WEAK]
strong_days = [d for d in dates if breadth.get(d, 0) >= WEAK]
P(f"弱市日(广度<{WEAK:.0f}%): {len(weak_days)} 天   强市日: {len(strong_days)} 天")
P(f"买入: 信号次日开盘 | 持有 {HOLD} 个交易日后收盘卖 | 手续费双边 {FEE*1e4:.0f}bp")
P("")


def run(events, label):
    """events: {signal_date: DataFrame/Series 或 dict(code->涨幅)}"""
    rets, mrets, codes_all = [], [], 0
    for d, codes in events.items():
        i = dates.index(d)
        j = i + 1              # 买入日
        k = i + 1 + HOLD       # 卖出日
        if k >= n:
            continue
        dj, dk = dates[j], dates[k]
        for c in codes:
            try:
                b = op.loc[dj, c]
                s = cl.loc[dk, c]
            except KeyError:
                continue
            if not (np.isfinite(b) and b > 0 and np.isfinite(s) and s > 0):
                continue
            rets.append((s / b - 1) * 100 - FEE * 100 * 2)
            codes_all += 1
        # 同期市场(所有股票同窗口等权)
        row_b = op.loc[dj]
        row_s = cl.loc[dk]
        ok = row_b.notna() & (row_b > 0) & row_s.notna() & (row_s > 0)
        if ok.sum() > 100:
            mrets.append(((row_s[ok] / row_b[ok] - 1) * 100).median())
    r = np.array(rets)
    m = np.array(mrets)
    if len(r) == 0:
        P(f"{label:<38} 无样本")
        return r
    win = (r > 0).mean() * 100
    deep = (r < -5).mean() * 100
    ex = r.mean() - (m.mean() if len(m) else 0)
    P(f"{label:<38} {len(r):>6}笔  胜率{win:>5.1f}%  均值{r.mean():>+6.2f}%  "
      f"亏超5%{deep:>5.1f}%  同期市场{m.mean() if len(m) else 0:>+6.2f}%  "
      f"超额{ex:>+6.2f}%")
    return r


# ---- 构造事件 ----
def build(day_list, cond):
    ev = {}
    for d in day_list:
        try:
            i = dates.index(d)
        except ValueError:
            continue
        if i + 1 + HOLD >= n:
            continue
        row = chg.loc[d].dropna()
        row = row[valid.loc[d].reindex(row.index).fillna(False)]
        sel = row[cond(row)]
        if len(sel):
            ev[d] = sel.index.tolist()
    return ev


P("=" * 92)
P("检验一: 弱市日(广度<50%)当天上涨的股票, 次日买入持5天")
P("-" * 92)
P("[对照0] 弱市日 买所有股票(不看涨跌)")
r_all_weak = run(build(weak_days, lambda r: r > -1e9), "  弱市·全股票")
P("[对照1] 强市日 买所有股票")
r_all_strong = run(build(strong_days, lambda r: r > -1e9), "  强市·全股票")
P("")
P("[主检验] 弱市日 当天上涨的股票, 按涨幅分档:")
run(build(weak_days, lambda r: (r > 0) & (r <= 3)), "  逆势涨 0~3%(温和)")
run(build(weak_days, lambda r: (r > 3) & (r <= 6)), "  逆势涨 3~6%(强势)")
run(build(weak_days, lambda r: r > 6), "  逆势涨 >6%(暴涨/涨停类)")
run(build(weak_days, lambda r: r > 0), "  逆势涨 全部(>0)")
P("")
P("[对照组] 强市日 当天同样涨幅的股票:")
run(build(strong_days, lambda r: (r > 0) & (r <= 3)), "  顺势涨 0~3%")
run(build(strong_days, lambda r: r > 6), "  顺势涨 >6%")
P("")

# ---- 检验二: 连续逆势(弱市日连续3天上涨) ----
P("=" * 92)
P("检验二: 弱市日'连续3天上涨'的股票(更强的逆势特征)")
P("-" * 92)
up3 = {}
for d in weak_days:
    try:
        i = dates.index(d)
    except ValueError:
        continue
    if i < 2 or i + 1 + HOLD >= n:
        continue
    c3 = chg.loc[dates[i-2]:d]
    mask = (c3 > 0).all(axis=0) & valid.loc[d].reindex(c3.columns).fillna(False)
    sel = mask[mask].index
    if len(sel):
        up3[d] = sel.tolist()
run(up3, "  弱市·连涨3天")
P("")

# ---- 检验三: 样本外(时间对半分) ----
P("=" * 92)
P("检验三: 样本外验证(前半 vs 后半) —— '弱市买逆势上涨股'")
P("-" * 92)
half = dates[n // 2]
weak_early = [d for d in weak_days if d < half]
weak_late = [d for d in weak_days if d >= half]
P(f"分割点: {half}   前半弱市日{len(weak_early)}天 / 后半{len(weak_late)}天")
run(build(weak_early, lambda r: r > 0), "  前半·逆势涨>0")
run(build(weak_late, lambda r: r > 0), "  后半·逆势涨>0(样本外)")
run(build(weak_early, lambda r: r > 6), "  前半·逆势涨>6%")
run(build(weak_late, lambda r: r > 6), "  后半·逆势涨>6%(样本外)")
P("")

# ---- 检验四: 弱市里跌幅榜(反向对照) ----
P("=" * 92)
P("检验四: 反向对照 —— 弱市日跌幅榜(验证'跌的更不能碰')")
P("-" * 92)
run(build(weak_days, lambda r: r < -6), "  弱市·跌>6%")
run(build(weak_days, lambda r: (r < -3) & (r >= -6)), "  弱市·跌3~6%")

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("\n".join(lines[-14:]))
print(f"\n完整输出: {OUT}")

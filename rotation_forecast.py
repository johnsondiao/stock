"""退潮期板块接力规律实证

回答一个问题: 市场从普涨转入退潮时, 接下来涨的是什么板块?
  - 是前期强势板块继续抱团 (强者恒强)?
  - 还是低位板块补涨 (高低切换)?

方法:
  1. 全市场周度广度 = 当周上涨个股占比
  2. 识别退潮事件: 上周广度>=55% 且 本周广度<=50%
  3. 对每次退潮, 记录退潮周行业收益前5的"前一周排名" → 看接力者是高位还是低位
  4. 再看退潮后1/2周, 退潮周前5行业的收益延续性
  5. 最后把"当前"状态映射到历史同类情形
"""
import io
import sqlite3

import numpy as np
import pandas as pd

DB = r"d:\vibecoding\stock\backend\data\stock.db"
MAP = r"d:\vibecoding\stock\industry_map.csv"
OUT = r"d:\vibecoding\stock\rotation_forecast.txt"

ind = pd.read_csv(MAP, encoding="utf-8-sig", dtype=str)
code2sec = dict(zip(ind["code"], ind["sector"]))

db = sqlite3.connect(DB, timeout=30)
df = pd.read_sql_query(
    "SELECT code, substr(date,1,10) d, close FROM daily_kline "
    "WHERE date >= '2025-01-01' ORDER BY code, date", db)
db.close()
df = df.sort_values(["code", "d"])
df = df.drop_duplicates(["code", "d"])
df["sector"] = df["code"].map(code2sec)
df = df.dropna(subset=["sector"])
df["dt"] = pd.to_datetime(df["d"])
df["week"] = df["dt"].dt.to_period("W-FRI")

# 每周每只股票的收盘价(取当周最后一个交易日)
px = df.groupby(["code", "sector", "week"])["close"].last().reset_index()
px["ret"] = px.groupby("code")["close"].pct_change() * 100

# 全市场广度: 当周上涨个股占比
wk_breadth = px.dropna(subset=["ret"]).groupby("week")["ret"].apply(
    lambda s: (s > 0).mean() * 100)

# 行业周收益中位数
sec_ret = px.dropna(subset=["ret"]).groupby(["week", "sector"])[
    "ret"].median().unstack()

weeks = wk_breadth.index.sort_values()
b = wk_breadth.reindex(weeks)

# ── 识别退潮事件 ──
events = []
for i in range(1, len(weeks)):
    w_prev, w_cur = weeks[i - 1], weeks[i]
    if b[w_prev] >= 55 and b[w_cur] <= 50:
        events.append((w_cur, b[w_prev], b[w_cur]))

o = io.open(OUT, "w", encoding="utf-8")
w = lambda s="": (print(s), o.write(s + "\n"))

w("退潮期板块接力规律实证 (2025-01 至今)")
w(f"周数 {len(weeks)}, 广度范围 {b.min():.0f}% ~ {b.max():.0f}%")
w()
w("== 全市场周度广度序列 (仅显示 <=55% 的压缩段) ==")
w("  " + "  ".join(f"{str(w)[5:]}:{v:.0f}" for w, v in b.items())[:1500])
w()

w("=" * 70)
w(f"退潮事件 (上周广度>=55% → 本周<=50%): 共 {len(events)} 次")
w("=" * 70)

# ── 每次退潮: 退潮周前5行业的前一周排名 ──
hi_carry, lo_rotate = 0, 0
rows = []
for w_cur, bp, bc in events:
    if w_cur not in sec_ret.index:
        continue
    r = sec_ret.loc[w_cur].dropna()
    if len(r) < 20:
        continue
    top5 = r.nlargest(5)
    # 前一周排名
    if w_cur - 1 in sec_ret.index:
        rp = sec_ret.loc[w_cur - 1].dropna()
        rank_prev = {s: rp.rank(ascending=False).get(s, np.nan) for s in top5.index}
        n_sec = len(rp)
        avg_rank = np.nanmean([rank_prev[s] for s in top5.index])
        is_high = avg_rank <= n_sec / 2
        hi_carry += is_high
        lo_rotate += not is_high
        names = ", ".join(f"{s}({v:+.1f},前名{rank_prev[s]:.0f}/{n_sec})"
                          for s, v in top5.items())
        rows.append((str(w_cur), bp, bc, avg_rank, n_sec, is_high, names))
        w(f"\n[{w_cur}] 广度 {bp:.0f}%→{bc:.0f}%")
        w(f"  退潮周前5: {names}")
        w(f"  前一周平均名次: {avg_rank:.0f}/{n_sec} → "
          f"{'高位延续(抱团)' if is_high else '低位切换(轮动)'}")

n_total = hi_carry + lo_rotate
w()
w("=" * 70)
w("结论统计")
w("=" * 70)
if n_total:
    w(f"退潮期接力者来自前期高位(强者恒强): {hi_carry}/{n_total} 次")
    w(f"退潮期接力者来自低位切换(高低切): {lo_rotate}/{n_total} 次")
    w(f"→ 退潮时更可能的接力方: "
      f"{'前期强势板块抱团延续' if hi_carry >= lo_rotate else '低位板块补涨'}")

# ── 退潮周前5行业在退潮后1/2周的延续性 ──
w()
w("=" * 70)
w("退潮周前5行业, 退潮后1周/2周的平均收益")
w("=" * 70)
fut1, fut2, base1 = [], [], []
for w_cur, bp, bc in events:
    wi = list(weeks).index(w_cur)
    if w_cur not in sec_ret.index:
        continue
    top5 = sec_ret.loc[w_cur].dropna().nlargest(5).index
    if wi + 1 < len(weeks) and weeks[wi + 1] in sec_ret.index:
        f1 = sec_ret.loc[weeks[wi + 1], top5].mean()
        b1 = sec_ret.loc[weeks[wi + 1]].mean()
        fut1.append(f1)
        base1.append(b1)
    if wi + 2 < len(weeks) and weeks[wi + 2] in sec_ret.index:
        fut2.append(sec_ret.loc[weeks[wi + 2], top5].mean())
if fut1:
    w(f"退潮周前5行业 → 后1周平均 {np.mean(fut1):+.2f}% "
      f"(全行业均值 {np.mean(base1):+.2f}%, 超额 {np.mean(fut1)-np.mean(base1):+.2f}%)")
if fut2:
    w(f"退潮周前5行业 → 后2周平均 {np.mean(fut2):+.2f}%")

# ── 当前状态映射 ──
w()
w("=" * 70)
w("当前状态映射 (最近4周)")
w("=" * 70)
for wk in weeks[-4:]:
    r = sec_ret.loc[wk].dropna()
    top3 = ", ".join(f"{s}({v:+.1f})" for s, v in r.nlargest(3).items())
    w(f"[{wk}] 广度 {b[wk]:.0f}%  前3: {top3}")

w()
w("=" * 70)
w("退潮环境下的历史强势行业 (退潮周平均收益排名前10)")
w("=" * 70)
perf = {}
for w_cur, bp, bc in events:
    if w_cur not in sec_ret.index:
        continue
    r = sec_ret.loc[w_cur].dropna()
    for s, v in r.items():
        perf.setdefault(s, []).append(v)
pl = [(s, np.mean(v), len(v)) for s, v in perf.items() if len(v) >= 5]
pl.sort(key=lambda x: -x[1])
for s, v, n in pl[:10]:
    w(f"  {s:<8} 退潮周平均 {v:+.2f}%  (经历 {n} 次退潮)")
w("  " + "-" * 30)
for s, v, n in pl[-5:]:
    w(f"  {s:<8} 退潮周平均 {v:+.2f}%  (经历 {n} 次退潮)")

o.close()
print(f"\n已保存: {OUT}")

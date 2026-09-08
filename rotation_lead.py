# 板块传导链挖掘: 谁涨完之后谁涨
# 方法: 5交易日非重叠采样 -> 行业收益中位数 -> 领先相关 + 条件收益检验
import io
import sqlite3
import time

import numpy as np
import pandas as pd

DB = r"d:\vibecoding\stock\backend\data\stock.db"
OUT = r"d:\vibecoding\stock\rotation_lead.txt"
W = 5            # 每个样本 = 5 个交易日
TOPN = 8         # 领涨行业取前 N
MINHIT = 8       # 最少触发次数才纳入统计

lines = []
def P(s=""):
    print(s)
    lines.append(s)

# ---------- 1) 数据 ----------
db = sqlite3.connect(DB, timeout=60)
# 注意: 日线数据 2025 年之前只有约 30 只股票, 全市场覆盖从 2025-01 开始
df = pd.read_sql_query(
    "SELECT code, substr(date,1,10) AS d, close FROM daily_kline "
    "WHERE date >= '2025-01-01'", db)
db.close()
ind = pd.read_csv(r"d:\vibecoding\stock\industry_map.csv",
                  encoding="utf-8-sig", dtype=str)[["code", "sector"]].dropna()

df["d"] = pd.to_datetime(df["d"])
df = df.merge(ind, on="code", how="inner").sort_values(["code", "d"])
px = df.pivot_table(index="d", columns="code", values="close", aggfunc="last")
px = px.sort_index()

# 5 日滚动收益, 每 5 天取一个不重叠样本
r5 = (px / px.shift(W) - 1).iloc[::W] * 100      # 转成百分比
code2sec = ind.set_index("code")["sector"]
sec = r5.T.groupby(code2sec).median().T
sec = sec.loc[:, sec.notna().sum(0) >= sec.shape[0] * 0.7]
sec = sec.iloc[1:]                       # 首期 shift 产生全 NaN

P(f"样本: {len(sec)} 期 × {sec.shape[1]} 个行业 "
  f"(每期 {W} 个交易日, 不重叠)")
P(f"时间: {sec.index[0].date()} ~ {sec.index[-1].date()}")
P("行业收益 = 行业内个股 5 日涨幅中位数")
P("=" * 62)

# ---------- 2) 延续性检验: 本期强势, 下期还强吗 ----------
ranks = sec.rank(axis=1, ascending=False)         # 1 = 最强
nsec = sec.shape[1]
nxt = sec.shift(-1)
hit_top = ranks <= TOPN
mkt = sec.mean(axis=1)                            # 每期全行业中位

P("")
P("【检验一】本期领涨的板块, 下一期还强吗")
P("-" * 62)
sub = nxt[hit_top.shift(0)].stack().dropna()      # 本期前N -> 下期收益
base = nxt.stack().dropna()
P(f"本期前{TOPN}名 -> 下期平均收益 {sub.mean():+.2f}%  "
  f"中位 {sub.median():+.2f}%  样本 {len(sub)}")
P(f"全行业基准      -> 下期平均收益 {base.mean():+.2f}%  "
  f"中位 {base.median():+.2f}%  样本 {len(base)}")
P(f">>> 超额 {sub.mean()-base.mean():+.2f}%")

# 按本期排名分层
P("")
P("按本期排名分层, 看下一期表现:")
for lo, hi, lab in [(1, 5, "第1-5名"), (6, 10, "第6-10名"),
                    (11, 20, "第11-20名"), (21, 99, "第21名以后")]:
    m = (ranks >= lo) & (ranks <= hi)
    v = nxt[m].stack().dropna()
    if len(v) > 30:
        bench_hit = pd.Series(v.index.get_level_values(0), index=v.index).map(mkt)
        P(f"  {lab:<10} 下期 {v.mean():+.2f}%  中位 {v.median():+.2f}%  "
          f"跑赢全行业 {(v > bench_hit).mean()*100:.0f}%")

# ---------- 3) 传导链: 领先相关 ----------
P("")
P("【检验二】传导链: A 板块涨完之后, 谁在下期涨得最好")
P("-" * 62)

cur = sec.iloc[:-1].values                        # t 期 (T-1, K)
nxtv = sec.iloc[1:].values                        # t+1 期 (T-1, K)
cols = list(sec.columns)
X = cur - cur.mean(0)
Y = nxtv - nxtv.mean(0)
num = X.T @ Y / X.shape[0]                        # (K, K): corr(X_i, Y_j)
den = np.outer(X.std(0), Y.std(0))
corr = num / np.where(den == 0, np.nan, den)      # corr[i,j] = A_t vs B_{t+1}

pairs = []
for i, a in enumerate(cols):
    row = corr[i]
    # A 本期 vs 各行业下期
    for j, b in enumerate(cols):
        if a == b:
            continue
        pairs.append((a, b, row[j]))
pf = pd.DataFrame(pairs, columns=["A", "B", "corr"])
pf["absr"] = pf["corr"].abs()

P("")
P("最强的 12 组『A 涨完 -> B 涨』关系 (相关系数):")
top = pf.sort_values("corr", ascending=False).head(12)
for _, r in top.iterrows():
    P(f"  {r['A']:<10} -> {r['B']:<10}  相关 {r['corr']:+.3f}")

P("")
P("最强的 6 组反向关系 (A 涨完 -> B 跌):")
for _, r in pf.sort_values("corr").head(6).iterrows():
    P(f"  {r['A']:<10} -> {r['B']:<10}  相关 {r['corr']:+.3f}")

# ---------- 4) 条件收益: A 进前 N 时, 各行业下期实际赚多少 ----------
P("")
P("【检验三】条件收益: 某板块进入前 %d 名后, 下一期各行业平均赚多少" % TOPN)
P("(只显示触发 >= %d 次、且下期超额最高的组合)" % MINHIT)
P("-" * 62)

base_by_period = sec.mean(axis=1)
res = []
for a in cols:
    hits = sec.index[ranks[a] <= TOPN]
    if len(hits) < MINHIT:
        continue
    periods = [sec.index.get_loc(h) + 1 for h in hits
               if sec.index.get_loc(h) + 1 < len(sec)]
    if len(periods) < MINHIT:
        continue
    sub_next = sec.iloc[periods]
    bench_v = base_by_period.iloc[periods].mean()
    for b in cols:
        if a == b:
            continue
        v = sub_next[b].dropna()
        if len(v) < MINHIT:
            continue
        t = v.mean() / (v.std() / np.sqrt(len(v))) if v.std() > 0 else 0
        res.append({"A": a, "B": b, "n": len(v), "mean": v.mean(),
                    "excess": v.mean() - bench_v, "win": (v > 0).mean() * 100,
                    "t": t})

rf = pd.DataFrame(res)
rf = rf[rf["t"] > 1.5].sort_values("excess", ascending=False)

P("")
P("A 领涨 -> B 下期平均收益(超额 / 上涨概率 / 触发次数):")
for _, r in rf.head(20).iterrows():
    P(f"  {r['A']:<10} -> {r['B']:<10} "
      f"{r['mean']:+.2f}%  超额{r['excess']:+.2f}%  "
      f"上涨{int(r['win']):>3}%  {int(r['n'])}次")

# ---------- 5) 当前状态 -> 下期展望 ----------
P("")
P("=" * 62)
P("【当前应用】最近一期(%s)谁在领涨, 历史上它们之后谁涨" % sec.index[-1].date())
P("=" * 62)

last = sec.iloc[-1].sort_values(ascending=False)
P("")
P(f"本期({W}日)最强的 {TOPN} 个行业:")
for s, v in last.head(TOPN).items():
    P(f"  {s:<10}{v:+.2f}%")

P("")
P("按历史传导规律, 下期值得关注的行业:")
rec = {}
for a in last.head(TOPN).index:
    sub = rf[rf["A"] == a].head(6)
    for _, r in sub.iterrows():
        rec[r["B"]] = rec.get(r["B"], 0) + r["excess"] * min(r["n"], 30) / 30
for b, sc in sorted(rec.items(), key=lambda x: -x[1])[:12]:
    P(f"  {b:<10} 综合分 {sc:+.2f}   本期表现 {last.get(b, float('nan')):+.2f}%")

# ---------- 6) 样本外验证: 前半段挖出的规律, 后半段还成立吗 ----------
P("")
P("=" * 62)
P("【检验四】样本外验证: 前半段挖出的传导链, 后半段还能赚钱吗")
P("=" * 62)

half = len(sec) // 2
def mine(sub_sec, topk=30):
    rk = sub_sec.rank(axis=1, ascending=False)
    nx = sub_sec.shift(-1)
    bp = sub_sec.mean(axis=1)
    out = []
    for a in sub_sec.columns:
        hits = sub_sec.index[rk[a] <= TOPN]
        pers = [sub_sec.index.get_loc(h) + 1 for h in hits
                if sub_sec.index.get_loc(h) + 1 < len(sub_sec)]
        if len(pers) < 6:
            continue
        sn = sub_sec.iloc[pers]
        bv = bp.iloc[pers].mean()
        for b in sub_sec.columns:
            if a == b:
                continue
            v = sn[b].dropna()
            if len(v) < 6:
                continue
            out.append((a, b, v.mean() - bv, len(v)))
    o = pd.DataFrame(out, columns=["A", "B", "excess", "n"])
    return o.sort_values("excess", ascending=False).head(topk)

def evaluate(pairs, sub_sec):
    rk = sub_sec.rank(axis=1, ascending=False)
    bp = sub_sec.mean(axis=1)
    vals = []
    for _, r in pairs.iterrows():
        hits = sub_sec.index[rk[r["A"]] <= TOPN]
        pers = [sub_sec.index.get_loc(h) + 1 for h in hits
                if sub_sec.index.get_loc(h) + 1 < len(sub_sec)]
        if not pers:
            continue
        sn = sub_sec.iloc[pers]
        bv = bp.iloc[pers].mean()
        v = sn[r["B"]].dropna()
        if len(v):
            vals.append(v.mean() - bv)
    return np.mean(vals) if vals else float("nan"), len(vals)

tr = sec.iloc[:half]
te = sec.iloc[half:]
mined = mine(tr)
tr_ex, tr_n = evaluate(mined, tr)
te_ex, te_n = evaluate(mined, te)
P(f"训练段 {tr.index[0].date()} ~ {tr.index[-1].date()} ({len(tr)}期)")
P(f"测试段 {te.index[0].date()} ~ {te.index[-1].date()} ({len(te)}期)")
P("")
P(f"用训练段挖出的 {len(mined)} 条最强传导链:")
P(f"  在训练段内回测  平均超额 {tr_ex:+.2f}%  ({tr_n} 条)")
P(f"  在测试段(样本外) 平均超额 {te_ex:+.2f}%  ({te_n} 条)")
if tr_ex > 0:
    keep = te_ex / tr_ex * 100 if tr_ex else 0
    P(f"  >>> 规律保留率 {keep:.0f}%")
    if keep < 30:
        P("  >>> 结论: 传导链基本是数据挖掘的噪声, 不可用于预测")
    elif keep < 70:
        P("  >>> 结论: 传导链有部分真实成分, 但大幅衰减, 需谨慎使用")
    else:
        P("  >>> 结论: 传导链在样本外依然有效, 具备预测价值")

# ---------- 7) 什么样的强势板块能延续 ----------
P("")
P("=" * 62)
P("【检验五】同样是强势板块, 哪种下期还能继续强")
P("=" * 62)

rk = sec.rank(axis=1, ascending=False)
nx = sec.shift(-1)
mkt = sec.mean(axis=1)
prev_rk = rk.shift(1)

conds = {}
# a) 连续两期在前8 vs 首次进入前8
conds["连续两期在前8"] = (rk <= TOPN) & (prev_rk <= TOPN)
conds["本期新进前8(上期不在)"] = (rk <= TOPN) & (prev_rk > TOPN)
# b) 趋势+动能双强: 20日(4期)均值排名前15 且 本期前8
ma4 = sec.rolling(4).mean()
conds["20日趋势+5日动能双强"] = (rk <= TOPN) & \
    (ma4.rank(axis=1, ascending=False) <= 15)
# c) 本期前8 但涨幅温和(不超过3%)
conds["前8且涨幅温和(<3%)"] = (rk <= TOPN) & (sec < 3)
conds["前8但已大涨(>5%)"] = (rk <= TOPN) & (sec > 5)
# d) 反过来: 买超跌的有效吗
n_all = sec.shape[1]
conds["上期排后10(超跌)"] = prev_rk > (n_all - 10)
conds["上期后10且已跌透(<-3%)"] = (prev_rk > (n_all - 10)) & (sec.shift(1) < -3)

P("")
P(f"{'条件':<22}{'样本':>6}{'下期收益':>10}{'超额':>9}{'跑赢全行业':>11}")
base_all = nx.stack().dropna().mean()
for lab, m in conds.items():
    v = nx[m].stack().dropna()
    if len(v) < 20:
        P(f"{lab:<22}样本不足")
        continue
    bh = pd.Series(v.index.get_level_values(0), index=v.index).map(mkt)
    P(f"{lab:<22}{len(v):>6}{v.mean():>9.2f}%{v.mean()-base_all:>+9.2f}%"
      f"{(v > bh).mean()*100:>10.0f}%")
P("")
P(f"参照: 全行业下期平均 {base_all:+.2f}%")

P("")
P("注: 相关系数为滞后一期(5个交易日)的皮尔逊相关; 条件收益已扣除同期全行业平均。")
P("样本期约 %d 个月, 结论随行情结构变化会失效, 需定期重算。" % (len(sec) * W // 21))

with io.open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("\nsaved", OUT)

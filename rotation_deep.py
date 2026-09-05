# 二阶段: 轮动规律量化检验
# 1. 板块热度持续性: 热板块下周是否继续热
# 2. 横截面预测: 本周密度排名 → 下周密度变化 (动量延续 vs 均值回归)
# 3. 领先-滞后矩阵: B板块本周热度 → A板块N周后热度 的传导链
import io
import numpy as np
import pandas as pd

dens = pd.read_csv(r"d:\vibecoding\stock\rotation_density.csv",
                   encoding="utf-8-sig", index_col=0)

# 排除极端周(全市场普涨, 密度>200% 无区分度)
big = dens.max(axis=1) > 2.0
print("极端普涨周(最大密度>200%):", big.sum(), "个")
dens_n = dens[~big]

out = io.open(r"d:\vibecoding\stock\rotation_deep.txt", "w", encoding="utf-8")

# ── 1. 热度持续性 ────────────────────────────────────────
top5_now = dens_n.apply(lambda r: set(r.nlargest(5).index), axis=1)
idx = list(top5_now.index)
overlaps = [len(top5_now[idx[i]] & top5_now[idx[i + 1]])
            for i in range(len(idx) - 1)]
ac1 = dens_n.corrwith(dens_n.shift(1)).mean()
out.write("== 热度持续性 ==\n")
out.write(f"相邻两周Top5板块平均重叠数: {np.mean(overlaps):.2f} / 5 "
          f"(随机基线≈{5 * 5 / 49:.2f})\n")
out.write(f"板块密度lag-1自相关均值: {ac1:.3f}\n\n")

# ── 2. 横截面排名 → 下周密度变化 ─────────────────────────
rank_now = dens_n.rank(axis=1, ascending=False)
dens_chg = dens_n.pct_change().shift(-1)
rho_list = []
for w in dens_n.index[:-1]:
    r, c = rank_now.loc[w], dens_chg.loc[w]
    m = r.notna() & c.notna() & np.isfinite(c)
    if m.sum() > 10:
        rho = r[m].corr(c[m], method="spearman")
        if not np.isnan(rho):
            rho_list.append(rho)
out.write("== 横截面预测: 本周密度排名 → 下周密度变化 ==\n")
out.write(f"周均Spearman相关: {np.mean(rho_list):.3f} (共{len(rho_list)}周)\n")
out.write("→ 正值=强者恒强(动量延续), 负值=均值回归(热点快速切换)\n\n")

# ── 3. 领先-滞后传导链 ───────────────────────────────────
active = dens_n.columns[dens_n.gt(0).sum() >= 10]
d = dens_n[active]
res = []
for lag in (1, 2, 3):
    fut = d.shift(-lag)
    pairs = []
    for a in active:
        for b in active:
            if a == b:
                continue
            v = d[a].corr(fut[b])  # A(t+lag) ~ B(t): B领先A
            if not np.isnan(v):
                pairs.append((v, b, a))
    pairs.sort(reverse=True)
    res.append((lag, pairs[:8]))

out.write("== 领先-滞后传导链 (B板块本周热度 → A板块N周后热度) ==\n")
for lag, top in res:
    out.write(f"-- lag {lag}周 --\n")
    for v, b, a in top:
        out.write(f"  {b} → {a}: {v:.3f}\n")
out.close()

print(f"相邻两周Top5重叠: {np.mean(overlaps):.2f}/5 (随机基线 {5*5/49:.2f})")
print(f"板块密度lag-1自相关均值: {ac1:.3f}")
print(f"横截面Spearman均值: {np.mean(rho_list):.3f}")
print("详细结果: rotation_deep.txt")

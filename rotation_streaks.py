# 热点驻留时长: 板块在Top3中连续出现的周数分布
import io
import numpy as np
import pandas as pd

dens = pd.read_csv(r"d:\vibecoding\stock\rotation_density.csv",
                   encoding="utf-8-sig", index_col=0)

streaks = []          # (sector, start_week, length)
cur = {}              # sector -> [start, length]
for w in dens.index:
    row = dens.loc[w]
    top3 = set(row[row > 0].nlargest(3).index.tolist())
    for sec in top3:
        if sec in cur:
            cur[sec][1] += 1
        else:
            cur[sec] = [w, 1]
    for sec in list(cur):
        if sec not in top3:
            s, l = cur.pop(sec)
            streaks.append((sec, s, l))
for sec, (s, l) in cur.items():
    streaks.append((sec, s, l))

lens = [l for _, _, l in streaks]
print(f"热点驻留段总数: {len(streaks)}")
print(f"平均驻留: {np.mean(lens):.1f} 周, 中位数: {np.median(lens):.0f} 周")
print(f"驻留>=2周占比: {sum(l >= 2 for l in lens) / len(lens):.0%}")
print(f"驻留>=4周占比: {sum(l >= 4 for l in lens) / len(lens):.0%}")

# 最长驻留案例
streaks.sort(key=lambda x: -x[2])
with io.open(r"d:\vibecoding\stock\rotation_streaks.txt", "w",
             encoding="utf-8") as f:
    f.write(f"热点驻留段总数 {len(streaks)}, 平均 {np.mean(lens):.1f} 周, "
            f"中位 {np.median(lens):.0f} 周, >=2周占比 "
            f"{sum(l >= 2 for l in lens) / len(lens):.0%}\n\n")
    f.write("── 最长驻留Top15 ──\n")
    for sec, s, l in streaks[:15]:
        f.write(f"{sec}: 从 {s} 起连续 {l} 周\n")
print("已保存 rotation_streaks.txt")

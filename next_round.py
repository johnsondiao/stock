# 当前与下一轮判断: 最近4周密度 + 萌芽检测 + 传导链匹配
import pandas as pd

dens = pd.read_csv(r"d:\vibecoding\stock\rotation_density.csv",
                   encoding="utf-8-sig", index_col=0)

last4 = dens.tail(4)
print("== 最近4周各板块密度 (只列有信号的) ==")
for w in last4.index:
    row = last4.loc[w]
    hot = row[row > 0].sort_values(ascending=False)
    print(f"\n{w}:")
    for s, v in hot.items():
        print(f"  {s}: {v:.0%}")

# 萌芽检测: 上周还是0或很低, 本周冒头(密度>0且环比大增)的板块
print("\n== 萌芽板块 (本周>0 且 较前3周均值显著上升) ==")
prev3 = dens.iloc[-4:-1].mean()
cur = dens.iloc[-1]
for s in cur.index:
    base = prev3[s]
    if cur[s] > 0 and cur[s] > max(base * 2, 0.05):
        print(f"  {s}: 前3周均值 {base:.0%} → 本周 {cur[s]:.0%}")

# 传导链匹配: 已知链条 上游→下游
chains = [
    ("石油行业", ["有色金属", "发电设备"]),
    ("煤炭行业", ["电力行业", "供水供气"]),
    ("农林牧渔", ["农药化肥", "化工行业"]),
    ("酿酒行业", ["环保行业", "房地产", "建筑建材", "机械行业", "金融行业"]),
    ("钢铁行业", ["有色金属", "电子器件"]),
    ("家电行业", ["电子器件", "塑料制品"]),
    ("交通运输", ["物资外贸"]),
    ("供水供气", ["开发区"]),
    ("纺织行业", ["金融行业", "塑料制品"]),
]
print("\n== 传导链状态: 上游热 + 下游冷 → 下一轮候选 ==")
for up, downs in chains:
    up_now = cur.get(up, 0)
    up_prev = prev3.get(up, 0)
    if up_now > 0.1 or up_prev > 0.1:
        cold = [(d, cur.get(d, 0)) for d in downs if cur.get(d, 0) < 0.05]
        hotd = [(d, cur.get(d, 0)) for d in downs if cur.get(d, 0) >= 0.05]
        print(f"  {up} (上周{up_prev:.0%}→本周{up_now:.0%}): 下游待启动 {cold}, 已启动 {hotd}")

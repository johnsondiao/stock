"""近期板块轮动实盘分析

口径:
  today  —— 实时快照 pct_change (盘中/午盘)
  r5     —— 最近 5 个交易日涨幅
  r5p    —— 前 5 个交易日涨幅 (t-10 ~ t-5), 用于对比"钱刚从哪里来"
  r20    —— 最近 20 个交易日涨幅
  d_rank —— 近5日排名 - 前5日排名, 负值=名次上升(新晋), 正值=退潮

行业收益一律取中位数, 抗个股极端值。
"""
import io
import sqlite3

import pandas as pd

DB = r"d:\vibecoding\stock\backend\data\stock.db"
MAP = r"d:\vibecoding\stock\industry_map.csv"
OUT = r"d:\vibecoding\stock\rotation_now.txt"

ind = pd.read_csv(MAP, encoding="utf-8-sig", dtype=str)
code2sec = dict(zip(ind["code"], ind["sector"]))

db = sqlite3.connect(DB, timeout=30)
df = pd.read_sql_query(
    "SELECT code, substr(date,1,10) d, close FROM daily_kline "
    "WHERE date >= (SELECT DISTINCT date FROM daily_kline "
    "ORDER BY date DESC LIMIT 1 OFFSET 29) ORDER BY code, date", db)
snap = pd.read_sql_query(
    "SELECT code, pct_change FROM realtime_snapshot WHERE volume>0", db)
db.close()

df = df.sort_values(["code", "d"])
g = df.groupby("code")["close"]
# 每只股票: 当前收盘 / 5日前 / 10日前 / 20日前
df["c0"] = g.transform("last")
df["c5"] = g.shift(5)
df["c10"] = g.shift(10)
df["c20"] = g.shift(20)

last = df.drop_duplicates("code", keep="last").set_index("code")
r5 = (last["c0"] / last["c5"] - 1) * 100
r5p = (last["c5"] / last["c10"] - 1) * 100
r20 = (last["c0"] / last["c20"] - 1) * 100

t = pd.DataFrame({"r5": r5, "r5p": r5p, "r20": r20})
t["sector"] = t.index.map(code2sec)
t = t.dropna(subset=["sector", "r5", "r5p"])

today = snap.set_index("code")["pct_change"].reindex(t.index)
t["today"] = today

sec = t.groupby("sector").agg(
    n=("r5", "size"),
    today=("today", "median"),
    r5=("r5", "median"),
    r5p=("r5p", "median"),
    r20=("r20", "median"),
)
sec = sec[sec["n"] >= 8]  # 剔除样本过少的行业

# 排名位移: 近5日 vs 前5日
sec["rank_now"] = sec["r5"].rank(ascending=False)
sec["rank_prev"] = sec["r5p"].rank(ascending=False)
sec["d_rank"] = sec["rank_now"] - sec["rank_prev"]  # 负=上升
sec["accel"] = sec["r5"] - sec["r5p"]               # 加速度

o = io.open(OUT, "w", encoding="utf-8")
w = lambda s="": (print(s), o.write(s + "\n"))

w(f"板块轮动实盘分析 · 数据截至今日快照, 日线最新 {df['d'].max()}")
w(f"有效行业 {len(sec)} 个, 覆盖股票 {len(t)} 只")
w()
w("=" * 74)
w("一 · 近 5 日最强 / 最弱行业 (中位数涨幅)")
w("=" * 74)
w(f"  {'行业':<8}{'只数':>5}{'今日':>8}{'近5日':>9}{'前5日':>9}{'近20日':>9}")
for s, r in sec.sort_values("r5", ascending=False).head(12).iterrows():
    w(f"  {s:<8}{int(r['n']):>5}{r['today']:>8.2f}{r['r5']:>9.2f}"
      f"{r['r5p']:>9.2f}{r['r20']:>9.2f}")
w("  " + "-" * 40)
for s, r in sec.sort_values("r5").head(6).iterrows():
    w(f"  {s:<8}{int(r['n']):>5}{r['today']:>8.2f}{r['r5']:>9.2f}"
      f"{r['r5p']:>9.2f}{r['r20']:>9.2f}")

w()
w("=" * 74)
w("二 · 轮动位移 (近5日排名 - 前5日排名, 负值=名次上升=资金新流入)")
w("=" * 74)
w(f"  {'行业':<8}{'名次变化':>9}{'加速度':>9}{'近5日':>9}{'前5日':>9}  状态")
for s, r in sec.sort_values("d_rank").head(10).iterrows():
    tag = "新晋/加速" if r["accel"] > 0 else "跌得少了"
    w(f"  {s:<8}{-r['d_rank']:>+9.0f}{r['accel']:>+9.2f}{r['r5']:>9.2f}"
      f"{r['r5p']:>9.2f}  {tag}")
w("  " + "-" * 50)
w("  —— 退潮 (名次下滑最多) ——")
for s, r in sec.sort_values("d_rank", ascending=False).head(8).iterrows():
    tag = "降温" if r["accel"] < 0 else "仍在涨但被超越"
    w(f"  {s:<8}{-r['d_rank']:>+9.0f}{r['accel']:>+9.2f}{r['r5']:>9.2f}"
      f"{r['r5p']:>9.2f}  {tag}")

w()
w("=" * 74)
w("三 · 近 20 日趋势 (判断谁是真主线, 不是一日游)")
w("=" * 74)
w(f"  {'行业':<8}{'近20日':>9}{'近5日':>9}{'今日':>8}  解读")
for s, r in sec.sort_values("r20", ascending=False).head(10).iterrows():
    if r["r5"] > r["r20"] / 4:
        tag = "持续走强"
    elif r["r5"] > 0:
        tag = "高位放缓"
    else:
        tag = "冲高回落"
    w(f"  {s:<8}{r['r20']:>9.2f}{r['r5']:>9.2f}{r['today']:>8.2f}  {tag}")

w()
w("=" * 74)
w("四 · 今日表现 (实时快照)")
w("=" * 74)
w(f"  {'行业':<8}{'今日':>8}{'近5日':>9}")
for s, r in sec.sort_values("today", ascending=False).head(8).iterrows():
    w(f"  {s:<8}{r['today']:>8.2f}{r['r5']:>9.2f}")
w("  " + "-" * 26)
for s, r in sec.sort_values("today").head(5).iterrows():
    w(f"  {s:<8}{r['today']:>8.2f}{r['r5']:>9.2f}")

sec.to_csv(r"d:\vibecoding\stock\rotation_sector.csv", encoding="utf-8-sig")
o.close()
print(f"\n已保存: {OUT}")

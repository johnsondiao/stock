# 日粒度密度(最近10个交易日) + 今日选股板块分布 → 当前轮判断
import io
import json
import sqlite3
import pandas as pd

DB = r"d:\vibecoding\stock\backend\data\stock.db"
MAP = r"d:\vibecoding\stock\industry_map.csv"
ind = pd.read_csv(MAP, encoding="utf-8-sig", dtype=str)
code2sec = dict(zip(ind["code"], ind["sector"]))
sector_size = ind.groupby("sector")["code"].nunique()

# 用小时线算日信号密度(2026数据完整): 每日每板块「当日发信号股数/板块股数」
# 信号口径同 rotation_analysis: MA24上穿MA60 8根内+站上双均线(取7月起数据预热均线)
db = sqlite3.connect(DB)
hourly = pd.read_sql_query(
    "SELECT code, substr(date,1,10) d, date, close FROM hourly_kline "
    "WHERE date>='2026-06-01' ORDER BY code, date", db)
db.close()

def sig_rolling(df, fast, slow, window):
    out = []
    for code, x in df.groupby("code", sort=False):
        maf = x["close"].rolling(fast).mean()
        mas = x["close"].rolling(slow).mean()
        cross = (maf > mas) & (maf <= mas).shift(1, fill_value=False)
        recent = cross.rolling(window, min_periods=1).max().gt(0)
        out.append(recent & (x["close"] > maf) & (x["close"] > mas))
    return pd.concat(out).sort_index()

hourly["hsig"] = sig_rolling(hourly, 24, 60, 8)
hourly = hourly[hourly["d"] >= "2026-08-17"]
hourly["sector"] = hourly["code"].map(code2sec)
hourly = hourly.dropna(subset=["sector"])

days = sorted(hourly["d"].unique())
lines = ["== 最近交易日 板块信号密度Top6 (小时线口径) =="]
for d in days:
    day = hourly[hourly["d"] == d]
    cnt = day[day["hsig"]].groupby("sector").size()
    dens = (cnt / sector_size).dropna().sort_values(ascending=False).head(6)
    top = ", ".join(f"{s}({v:.0%})" for s, v in dens.items())
    lines.append(f"{d} (信号股 {int(day['hsig'].sum())} 只): {top}")

# 当日新金叉(更及时): 当日发生cross的
def fresh_cross(df, fast, slow):
    out = []
    for code, x in df.groupby("code", sort=False):
        maf = x["close"].rolling(fast).mean()
        mas = x["close"].rolling(slow).mean()
        out.append((maf > mas) & (maf <= mas).shift(1, fill_value=False))
    return pd.concat(out).sort_index()

hourly["cross"] = fresh_cross(hourly, 24, 60)
lines.append("\n== 最近交易日 当日新金叉板块分布 ==")
for d in days:
    day = hourly[hourly["d"] == d]
    cnt = day[day["cross"]].groupby("sector").size()
    dens = (cnt / sector_size).dropna().sort_values(ascending=False).head(6)
    tot = int(day["cross"].sum())
    top = ", ".join(f"{s}({int(cnt[s])})" for s, v in dens.items())
    lines.append(f"{d}: 新金叉 {tot} 只 → {top}")

# 今14只选股的板块分布
with open(r"d:\vibecoding\stock\screen_result_today.json", encoding="utf-8") as f:
    res = json.load(f)
lines.append("\n== 今天实时选股14只 板块分布 ==")
cnt2 = {}
for r in res["results"]:
    sec = code2sec.get(r["code"], "未分类")
    cnt2[sec] = cnt2.get(sec, 0) + 1
for s, c in sorted(cnt2.items(), key=lambda x: -x[1]):
    names = [r["name"] for r in res["results"] if code2sec.get(r["code"]) == s]
    lines.append(f"  {s}: {c} 只 ({'/'.join(names)})")

with io.open(r"d:\vibecoding\stock\current_round.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("saved current_round.txt")

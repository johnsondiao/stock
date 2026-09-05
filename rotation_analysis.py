# ma_combo 信号历史回放 + 板块轮动分析
# 信号定义(忠实于 ma_combo 闸门/入场逻辑, 日频重采样):
#   日线信号: MA12 上穿 MA60 的金叉发生在最近3日内, 且收盘站上快慢均线 (≈闸门C+入场)
#   小时信号: MA24 上穿 MA60 的金叉发生在最近8根(约2日)内, 且收盘站上快慢均线 (≈闸门A+B)
import io
import sqlite3
import pandas as pd

DB = r"d:\vibecoding\stock\backend\data\stock.db"
MAP = r"d:\vibecoding\stock\industry_map.csv"

ind = pd.read_csv(MAP, encoding="utf-8-sig", dtype=str)
code2sec = dict(zip(ind["code"], ind["sector"]))
sector_size = ind.groupby("sector")["code"].nunique()


def sig_rolling(df, fast, slow, window):
    """组内: 金叉后 window 根内且收盘站上快慢线 → True"""
    out = []
    for code, x in df.groupby("code", sort=False):
        maf = x["close"].rolling(fast).mean()
        mas = x["close"].rolling(slow).mean()
        below = maf <= mas
        cross = (maf > mas) & below.shift(1, fill_value=False)
        recent = cross.rolling(window, min_periods=1).max().gt(0)
        sig = recent & (x["close"] > maf) & (x["close"] > mas)
        out.append(sig)
    return pd.concat(out).sort_index()


db = sqlite3.connect(DB)

# ── 日线信号 (2025起全市场) ──────────────────────────────
daily = pd.read_sql_query(
    "SELECT code, substr(date,1,10) d, close FROM daily_kline "
    "WHERE date>=? ORDER BY code, date", db, params=("2024-06-01",))
print(f"日线行数: {len(daily)}")
daily["dsig"] = sig_rolling(daily, 12, 60, 3)
daily = daily[daily["d"] >= "2025-01-01"]
print("日线信号条数:", int(daily["dsig"].sum()))

# ── 小时信号 (2026起全市场) ──────────────────────────────
hourly = pd.read_sql_query(
    "SELECT code, substr(date,1,10) d, close FROM hourly_kline "
    "WHERE date>=? ORDER BY code, date", db, params=("2025-12-01",))
print(f"小时行数: {len(hourly)}")
hourly["hsig"] = sig_rolling(hourly, 24, 60, 8)
hourly = hourly[hourly["d"] >= "2026-01-01"]
print("小时信号条数:", int(hourly["hsig"].sum()))
db.close()

daily["sector"] = daily["code"].map(code2sec)
hourly["sector"] = hourly["code"].map(code2sec)
daily = daily.dropna(subset=["sector"])
hourly = hourly.dropna(subset=["sector"])

daily["week"] = pd.to_datetime(daily["d"]).dt.to_period("W-SUN").astype(str)
hourly["week"] = pd.to_datetime(hourly["d"]).dt.to_period("W-SUN").astype(str)

# ── 周度信号密度矩阵: (该板块当周信号股数) / 板块总股数 ──
d_cnt = daily[daily["dsig"]].groupby(["week", "sector"]).size()
h_cnt = hourly[hourly["hsig"]].groupby(["week", "sector"]).size()

weeks = sorted(set(daily["week"]) | set(hourly["week"]))
sectors = sorted(ind["sector"].unique())
dens = pd.DataFrame(0.0, index=weeks, columns=sectors)
for (w, sec), v in d_cnt.items():
    if w in dens.index:
        dens.at[w, sec] += v
for (w, sec), v in h_cnt.items():
    if w in dens.index:
        dens.at[w, sec] += v
dens = dens.div(dens.columns.map(sector_size), axis=1).fillna(0.0)
dens.to_csv(r"d:\vibecoding\stock\rotation_density.csv", encoding="utf-8-sig")


def topk(row, k=3):
    r = row[row > 0].sort_values(ascending=False).head(k)
    return ", ".join(f"{s}({v:.0%})" for s, v in r.items()) if len(r) else "-"


weekly_top = dens.apply(topk, axis=1)

# ── 预测性: 信号密度 与 板块未来一周收益 相关性 ─────────
dr = daily[["code", "d", "close", "sector", "week"]].copy()
dr["ret"] = dr.groupby("code")["close"].pct_change()
sec_ret = dr.groupby(["week", "sector"])["ret"].mean().unstack()
fwd_ret = sec_ret.shift(-1)  # 下一周收益

pairs = pd.DataFrame({"dens": dens.stack(), "fwd": fwd_ret.stack()}).dropna()
corr = pairs["dens"].corr(pairs["fwd"])

sec_q75 = dens.quantile(0.75)
lvl_sec = pairs.index.get_level_values(1).map(sec_q75)
hi = pairs[pairs["dens"] > lvl_sec]
lo = pairs[(pairs["dens"] > 0) & (pairs["dens"] <= lvl_sec)]

print(f"\n信号密度与下周板块收益相关性: {corr:.4f}")
print(f"高密度组样本 {len(hi)}, 平均下周收益 {hi['fwd'].mean()*100:.2f}%")
print(f"低密度组样本 {len(lo)}, 平均下周收益 {lo['fwd'].mean()*100:.2f}%")

with io.open(r"d:\vibecoding\stock\rotation_stats.txt", "w",
             encoding="utf-8") as f:
    f.write(f"分析区间: {min(weeks)} ~ {max(weeks)}, 周数 {len(weeks)}\n")
    f.write(f"日线信号总数 {int(daily['dsig'].sum())}, "
            f"小时信号总数 {int(hourly['hsig'].sum())}\n")
    f.write(f"信号密度与下周板块收益相关系数: {corr:.4f}\n")
    f.write(f"高密度组: 样本 {len(hi)}, 平均下周收益 {hi['fwd'].mean()*100:.2f}%\n")
    f.write(f"低密度组: 样本 {len(lo)}, 平均下周收益 {lo['fwd'].mean()*100:.2f}%\n")
    f.write("\n── 每周信号密度Top3板块 ──\n")
    for w, t in weekly_top.items():
        f.write(f"{w}  {t}\n")
print("\n结果已保存: rotation_density.csv / rotation_stats.txt")

# 9/3 早盘决策: 竞价价格 + 昨收口径MA12/60 + 市场广度 → 持有/平仓清单
import io
import re
import time
import sqlite3
import requests
import pandas as pd

HOLD = [
    ("sh600218", "全柴动力", 7.68, 100),
    ("sz000089", "深圳机场", 6.59, 100),
    ("sz000900", "现代投资", 3.72, 100),
    ("sh600261", "阳光照明", 3.31, 100),
    ("sh600202", "哈空调",   5.23, 100),
    ("sz000498", "山东路桥", 5.00, 100),
    ("sh600195", "中牧股份", 6.90, 100),
    ("sh601949", "中国出版", 5.37, 100),
    ("sh600051", "宁波联合", 6.53, 100),
    ("sh600497", "驰宏锌锗", 10.45, 100),
    ("sz000630", "铜陵有色", 6.775, 200),
]
HEAD = {"User-Agent": "Mozilla/5.0",
        "Referer": "https://finance.sina.com.cn"}

# 1. 市场广度(今晨快照)
db = sqlite3.connect(r"d:\vibecoding\stock\backend\data\stock.db")
adv, dec, tot, t_snap = db.execute(
    "SELECT SUM(pct_change>0), SUM(pct_change<0), COUNT(*), MAX(updated_at) "
    "FROM realtime_snapshot WHERE volume>0").fetchone()
db.close()

# 2. 竞价实时价
r = requests.get("https://hq.sinajs.cn/list=" + ",".join(s for s, *_ in HOLD),
                 headers=HEAD, timeout=10)
r.encoding = "gbk"
rt = {}
for m in re.finditer(r'hq_str_(\w+)="([^"]+)"', r.text):
    f = m.group(2).split(",")
    price = float(f[3]) or float(f[2])
    rt[m.group(1)] = {"price": price, "pre": float(f[2]),
                      "open": float(f[1]),
                      "pct": (price / float(f[2]) - 1) * 100 if float(f[2]) else 0,
                      "time": f[31]}

lines = [f"== 9/3 早盘决策 (广度快照 {t_snap}: 涨{adv}/跌{dec}/{tot}) ==", ""]

# 3. 每只: 昨收口径 MA12/MA60 + 竞价位置
for sym, name, cost, qty in HOLD:
    u = ("https://quotes.sina.cn/cn/api/json_v2.php/"
         f"CN_MarketDataService.getKLineData?symbol={sym}"
         "&scale=240&ma=no&datalen=80")
    try:
        data = requests.get(u, headers=HEAD, timeout=10).json()
        df = pd.DataFrame(data)
        df["close"] = df["close"].astype(float)
        # 只取到昨日(9/2)的收盘, 今日盘中bar不参与均线判定
        df = df[df["day"] <= "2026-09-02"]
        ma12 = df["close"].rolling(12).mean().iloc[-1]
        ma60 = df["close"].rolling(60).mean().iloc[-1]
        last_close = df["close"].iloc[-1]
    except Exception as e:
        ma12 = ma60 = last_close = float("nan")
    q = rt.get(sym, {})
    p = q.get("price", 0)
    gap = q.get("pct", 0)
    pos12 = "上方" if p > ma12 else "下方"
    pos60 = "上方" if p > ma60 else "下方"
    pnl = (p / cost - 1) * 100
    lines.append(
        f"{name} {sym[2:]}: 竞价{p:.2f} ({gap:+.2f}%) 盈亏{pnl:+.2f}% | "
        f"昨收{last_close:.2f} MA12={ma12:.2f}({pos12}) MA60={ma60:.2f}({pos60})")
    time.sleep(0.4)

with io.open(r"d:\vibecoding\stock\morning_plan.txt", "w",
             encoding="utf-8") as f:
    f.write("\n".join(lines))
print("saved morning_plan.txt")

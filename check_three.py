# 分析三只指定股票: 拓斯达300607 / 科新机电300092 / 上海电气601727
# 创业板两只不在本地库(主板范围), 直接走新浪实时+日线接口
import io
import json
import re
import sqlite3
import requests
import pandas as pd

STOCKS = [
    ("sz300607", "拓斯达"),
    ("sz300092", "科新机电"),
    ("sh601727", "上海电气"),
]
HEAD = {"User-Agent": "Mozilla/5.0",
        "Referer": "https://finance.sina.com.cn"}
out = io.open(r"d:\vibecoding\stock\three_stocks.txt", "w", encoding="utf-8")

# 1. 实时行情(新浪)
syms = ",".join(s for s, _ in STOCKS)
r = requests.get(f"http://hq.sinajs.cn/list={syms}", headers=HEAD, timeout=10)
r.encoding = "gbk"
rt = {}
for line in r.text.strip().splitlines():
    m = re.match(r'var hq_str_(s[hz]\d{6})="(.*)";', line)
    if m and m.group(2):
        f = m.group(2).split(",")
        rt[m.group(1)] = {
            "name": f[0], "open": float(f[1]), "pre": float(f[2]),
            "price": float(f[3]), "high": float(f[4]), "low": float(f[5]),
            "volume": float(f[8]), "date": f[30], "time": f[31],
        }

# 2. 本地库覆盖检查
db = sqlite3.connect(r"d:\vibecoding\stock\backend\data\stock.db")
for sym, label in STOCKS:
    code = sym[2:]
    n_d = db.execute("SELECT COUNT(*) FROM daily_kline WHERE code=?",
                     (code,)).fetchone()[0]
    n_h = db.execute("SELECT COUNT(*) FROM hourly_kline WHERE code=?",
                     (code,)).fetchone()[0]
    out.write(f"{label} {code}: 本地日线 {n_d} 根, 小时线 {n_h} 根")
    if code in rt or sym in rt:
        q = rt.get(sym, {})
        pct = (q["price"] / q["pre"] - 1) * 100 if q.get("pre") else 0
        out.write(f" | 实时 {q['price']} ({pct:+.2f}%) @ {q.get('time')}")
    out.write("\n")

# 3. 日线技术面(新浪 scale=240, 取300根)
out.write("\n== 日线技术面 (MA12/MA60 金叉状态) ==\n")
for sym, label in STOCKS:
    try:
        u = ("https://quotes.sina.cn/cn/api/json_v2.php/"
             f"CN_MarketDataService.getKLineData?symbol={sym}"
             "&scale=240&ma=no&datalen=320")
        data = requests.get(u, headers=HEAD, timeout=10).json()
        df = pd.DataFrame(data)
        df["close"] = df["close"].astype(float)
        df["maf"] = df["close"].rolling(12).mean()
        df["mas"] = df["close"].rolling(60).mean()
        last = df.iloc[-1]
        prev = df.iloc[-2]
        price, maf, mas = last["close"], last["maf"], last["mas"]
        below_prev = prev["maf"] <= prev["mas"]
        cross_today = maf > mas and below_prev
        # 距最近金叉天数
        cross_mask = (df["maf"] > df["mas"]) & (
            (df["maf"] <= df["mas"]).shift(1, fill_value=False))
        since = None
        if cross_mask.any():
            idx = df.index[cross_mask][-1]
            since = len(df) - 1 - idx
        chg5 = (price / df["close"].iloc[-6] - 1) * 100
        chg20 = (price / df["close"].iloc[-21] - 1) * 100
        status = "金叉当天" if cross_today else (
            f"多头排列(金叉距今{since}日)" if (maf > mas and since is not None)
            else ("空头/整理" if maf <= mas else "多头"))
        above = "站上双均线" if price > maf and price > mas else "未站上均线"
        out.write(f"{label}({sym}): {price} | {status} | {above}\n")
        out.write(f"   MA12={maf:.2f} MA60={mas:.2f} | "
                  f"近5日 {chg5:+.1f}% 近20日 {chg20:+.1f}% | "
                  f"最后日期 {last['day']}\n")
    except Exception as e:
        out.write(f"{label}({sym}): 获取失败 {e}\n")

out.close()
print("saved three_stocks.txt")

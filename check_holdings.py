# 持仓体检: 日线/小时线/5分钟多周期状态 + 板块 + 实时竞价价格
import io
import re
import sqlite3
import requests
import pandas as pd

HOLD = [
    # (代码, 名称, 成本, 股数)
    ("600218", "全柴动力", 7.68, 100),
    ("000089", "深圳机场", 6.66, 100),
    ("000900", "现代投资", 3.72, 100),
    ("600261", "阳光照明", 3.31, 100),
    ("600202", "哈空调",   8.32, 100),
    ("000498", "山东路桥", 8.47, 100),
    ("600195", "中牧股份", 6.90, 100),
    ("601949", "中国出版", 7.63, 100),
    ("600051", "宁波联合", 6.53, 100),
    ("002062", "宏润建设", 8.25, 100),
    ("600123", "兰花科创", 7.46, 100),
    ("600497", "驰宏锌锗", 10.45, 100),
    ("000630", "铜陵有色", 6.775, 200),
]
DB = r"d:\vibecoding\stock\backend\data\stock.db"

ind = pd.read_csv(r"d:\vibecoding\stock\industry_map.csv",
                  encoding="utf-8-sig", dtype=str)
code2sec = dict(zip(ind["code"], ind["sector"]))

# ── 实时竞价/最新价 ─────────────────────────────────────
def sina_sym(c):
    return f"sh{c}" if c.startswith(("6", "9")) else f"sz{c}"

syms = ",".join(sina_sym(c) for c, *_ in HOLD)
r = requests.get(f"https://hq.sinajs.cn/list={syms}", headers={
    "User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"
}, timeout=10)
r.encoding = "gbk"
rt = {}
for line in r.text.strip().splitlines():
    m = re.match(r'var hq_str_(s[hz]\d{6})="(.*)";', line)
    if m and m.group(2):
        f = m.group(2).split(",")
        price = float(f[3]) or float(f[2])
        rt[m.group(1)[2:]] = {"price": price, "pre": float(f[2]),
                              "time": f[31]}

# ── K线多周期状态 ───────────────────────────────────────
db = sqlite3.connect(DB)

def ma_state(code, table, fast, slow):
    """返回 (多头?, 价格站上双均线?, 距最近金叉/死叉根数, 距今事件)"""
    df = pd.read_sql_query(
        f"SELECT close FROM {table} WHERE code=? ORDER BY date", db,
        params=(code,))
    if len(df) < slow + 2:
        return None
    c = df["close"]
    maf, mas = c.rolling(fast).mean(), c.rolling(slow).mean()
    bull = maf.iloc[-1] > mas.iloc[-1]
    above = c.iloc[-1] > maf.iloc[-1] and c.iloc[-1] > mas.iloc[-1]
    cross = (maf > mas) != (maf.shift(1) > mas.shift(1).fillna(False))
    cross = cross & maf.notna() & mas.notna() & maf.shift(1).notna()
    if cross.any():
        idx = df.index[cross][-1]
        ago = len(df) - 1 - idx
        event = "金叉" if bull else "死叉"
    else:
        ago, event = None, "?"
    return bull, above, ago, event

lines = []
for code, name, cost, qty in HOLD:
    price = rt.get(code, {}).get("price", 0)
    t = rt.get(code, {}).get("time", "?")
    pnl = (price / cost - 1) * 100 if price else 0
    d = ma_state(code, "daily_kline", 12, 60)
    h = ma_state(code, "hourly_kline", 24, 60)
    f5 = ma_state(code, "kline_5min", 12, 288)
    sec = code2sec.get(code, "未分类")

    def fmt(s):
        if s is None:
            return "数据不足"
        bull, above, ago, event = s
        pos = "多头" if bull else "空头"
        up = "价在线上" if above else "价破均线"
        ago_s = f"{event}距今{ago}根" if ago is not None else ""
        return f"{pos}/{up}/{ago_s}"

    lines.append(f"{name} {code} [{sec}] 现价{price:.2f}({t}) 成本{cost} 盈亏{pnl:+.2f}%")
    lines.append(f"   日线: {fmt(d)}")
    lines.append(f"   小时: {fmt(h)}")
    lines.append(f"   5分: {fmt(f5)}")
    lines.append("")

db.close()
with io.open(r"d:\vibecoding\stock\holdings_check.txt", "w",
             encoding="utf-8") as f:
    f.write("\n".join(lines))
print("saved holdings_check.txt")

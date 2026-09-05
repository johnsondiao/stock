# 持仓复检(修正成本版): 技术状态 + 实时价 + 市场广度
import io
import re
import sqlite3
import requests
import pandas as pd

HOLD = [
    ("600218", "全柴动力", 7.68, 100),
    ("000089", "深圳机场", 6.59, 100),
    ("000900", "现代投资", 3.72, 100),
    ("600261", "阳光照明", 3.31, 100),
    ("600202", "哈空调",   5.23, 100),
    ("000498", "山东路桥", 5.00, 100),
    ("600195", "中牧股份", 6.90, 100),
    ("601949", "中国出版", 5.37, 100),
    ("600051", "宁波联合", 6.53, 100),
    ("600497", "驰宏锌锗", 10.45, 100),
    ("000630", "铜陵有色", 6.775, 200),
]
DB = r"d:\vibecoding\stock\backend\data\stock.db"

ind = pd.read_csv(r"d:\vibecoding\stock\industry_map.csv",
                  encoding="utf-8-sig", dtype=str)
code2sec = dict(zip(ind["code"], ind["sector"]))

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
        pre = float(f[2])
        rt[m.group(1)[2:]] = {"price": price,
                              "pct": (price / pre - 1) * 100 if pre else 0,
                              "time": f[31]}

db = sqlite3.connect(DB)

# 市场广度: 今晨快照涨跌家数
adv, dec, tot = db.execute(
    "SELECT SUM(pct_change>0), SUM(pct_change<0), COUNT(*) "
    "FROM realtime_snapshot WHERE volume>0").fetchone()
t_snap = db.execute("SELECT MAX(updated_at) FROM realtime_snapshot").fetchone()[0]

def ma_state(code, table, fast, slow):
    df = pd.read_sql_query(
        f"SELECT close FROM {table} WHERE code=? ORDER BY date", db,
        params=(code,))
    if len(df) < slow + 2:
        return None
    c = df["close"]
    maf, mas = c.rolling(fast).mean(), c.rolling(slow).mean()
    diff = (maf > mas)
    prev = diff.shift(1).fillna(False)
    cross = (diff != prev) & maf.notna() & mas.notna() & maf.shift(1).notna()
    bull = bool(diff.iloc[-1])
    above = bool(c.iloc[-1] > maf.iloc[-1] and c.iloc[-1] > mas.iloc[-1])
    if cross.any():
        idx = df.index[cross][-1]
        ago = len(df) - 1 - idx
        event = "金叉" if bull else "死叉"
    else:
        ago, event = None, "?"
    return bull, above, ago, event

def fmt(s):
    if s is None:
        return "数据不足"
    bull, above, ago, event = s
    return (f"{'多头' if bull else '空头'}/{'价在线上' if above else '价破均线'}"
            f"/{event}{ago}根")

lines = [f"市场广度({t_snap}): 上涨 {adv} / 下跌 {dec} / 总 {tot}", ""]
for code, name, cost, qty in HOLD:
    q = rt.get(code, {})
    price = q.get("price", 0)
    t = q.get("time", "?")
    pnl = (price / cost - 1) * 100 if price else 0
    d = ma_state(code, "daily_kline", 12, 60)
    h = ma_state(code, "hourly_kline", 24, 60)
    f5 = ma_state(code, "kline_5min", 12, 288)
    sec = code2sec.get(code, "未分类")
    lines.append(f"{name} {code} [{sec}] {price:.2f} 今{q.get('pct', 0):+.2f}% "
                 f"({t}) 成本{cost} 盈亏{pnl:+.2f}%")
    lines.append(f"   日线:{fmt(d)} | 小时:{fmt(h)} | 5分:{fmt(f5)}")

db.close()
with io.open(r"d:\vibecoding\stock\holdings_recheck.txt", "w",
             encoding="utf-8") as f:
    f.write("\n".join(lines))
print("saved holdings_recheck.txt")

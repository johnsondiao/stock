# 尾盘复核: 收盘价格/止损位/广度/持仓技术状态 + 明日预案
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
STOPS = {"000630": 6.30}  # 止损位
DB = r"d:\vibecoding\stock\backend\data\stock.db"

def sina_sym(c):
    return f"sh{c}" if c.startswith(("6", "9")) else f"sz{c}"

r = requests.get(
    "https://hq.sinajs.cn/list=" + ",".join(sina_sym(c) for c, *_ in HOLD),
    headers={"User-Agent": "Mozilla/5.0",
             "Referer": "https://finance.sina.com.cn"}, timeout=10)
r.encoding = "gbk"
rt = {}
for m in re.finditer(r'hq_str_(\w+)="([^"]+)"', r.text):
    f = m.group(2).split(",")
    price = float(f[3]) or float(f[2])
    rt[m.group(1)[2:]] = {"name": f[0], "price": price, "pre": float(f[2]),
                          "pct": (price / float(f[2]) - 1) * 100 if float(f[2]) else 0,
                          "low": float(f[5]), "time": f[31]}

db = sqlite3.connect(DB)
adv, dec, tot, t_snap = db.execute(
    "SELECT SUM(pct_change>0), SUM(pct_change<0), COUNT(*), MAX(updated_at) "
    "FROM realtime_snapshot WHERE volume>0").fetchone()

def daily_ma(code):
    """日线 MA12/MA60 最新值(含今日修补前的DB数据) + 多空"""
    df = pd.read_sql_query(
        "SELECT close FROM daily_kline WHERE code=? ORDER BY date", db,
        params=(code,))
    if len(df) < 62:
        return None
    c = df["close"]
    return c.rolling(12).mean().iloc[-1], c.rolling(60).mean().iloc[-1]

lines = [f"== 尾盘复核 (快照时间 {t_snap}) ==",
         f"市场广度: 上涨 {adv} / 下跌 {dec} / 总 {tot}",
         f"广度占比: {adv/tot*100:.1f}%  (早盘9:45为11.6%, 昨日为普涨)", ""]
total_pnl = 0.0
for code, name, cost, qty in HOLD:
    q = rt.get(code, {})
    price = q.get("price", 0)
    pnl = (price - cost) * qty
    total_pnl += pnl
    mark = ""
    if code in STOPS:
        s = STOPS[code]
        mark = " ⚠️跌破止损!" if price < s else f" (止损位{s}, 距离{(price/s-1)*100:+.1f}%)"
    ma = daily_ma(code)
    ma_s = f"MA12={ma[0]:.2f}/MA60={ma[1]:.2f}" if ma else ""
    lines.append(f"{name} {code}: 收盘{price:.2f} {q.get('pct',0):+.2f}% "
                 f"日低{q.get('low',0):.2f} | 盈亏 {pnl:+.0f}元 "
                 f"({(price/cost-1)*100:+.2f}%){mark} | {ma_s}")

lines.append(f"\n组合当日浮动盈亏合计: {total_pnl:+.0f} 元")
db.close()
with io.open(r"d:\vibecoding\stock\eod_check.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("saved eod_check.txt")

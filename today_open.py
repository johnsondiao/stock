# 9/4 开盘前: 广度 + 持仓实时 + 关键位
import io
import re
import sqlite3
import requests

HOLD = [
    ("sh601949", "中国出版", 5.37),
    ("sh600218", "全柴动力", 7.787),
    ("sz000089", "深圳机场", 6.59),
    ("sh600202", "哈空调", 5.23),
    ("sh600261", "阳光照明", 3.31),
    ("sh600497", "驰宏锌锗", 10.45),
    ("sz000900", "现代投资", 3.72),
    ("sz000630", "铜陵有色", 6.775),
]
MA12 = {"哈空调": 5.114, "阳光照明": 3.200, "全柴动力": 7.649,
        "深圳机场": 6.524, "中国出版": 5.219}

db = sqlite3.connect(r"d:\vibecoding\stock\backend\data\stock.db")
adv, dec, tot, t_snap = db.execute(
    "SELECT SUM(pct_change>0), SUM(pct_change<0), COUNT(*), MAX(updated_at) "
    "FROM realtime_snapshot WHERE volume>0").fetchone()
db.close()

r = requests.get(
    "https://hq.sinajs.cn/list=" + ",".join(s for s, *_ in HOLD),
    headers={"User-Agent": "Mozilla/5.0",
             "Referer": "https://finance.sina.com.cn"}, timeout=10)
r.encoding = "gbk"
lines = [f"市场广度快照 {t_snap}: 涨{adv}/跌{dec}/{tot} "
         f"({adv/tot*100:.0f}%)", ""]
for m in re.finditer(r'hq_str_(\w+)="([^"]+)"', r.text):
    f = m.group(2).split(",")
    name = f[0]
    price, pre = float(f[3]), float(f[2])
    pct = (price / pre - 1) * 100 if pre else 0
    ma = MA12.get(name)
    ma_s = f" | MA12={ma:.2f} {'上' if price > ma else '下❗'}" if ma else ""
    lines.append(f"{name} {m.group(1)[2:]}: {price:.2f} ({pct:+.2f}%) "
                 f"@{f[31]}{ma_s}")

with io.open(r"d:\vibecoding\stock\today_open.txt", "w", encoding="utf-8") as fp:
    fp.write("\n".join(lines))
print("saved")

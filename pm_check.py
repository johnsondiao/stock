# 9/4 下午盘中核查: 纪律线 + 涨停封板状态 + 广度
import io
import re
import sqlite3
import requests

STOCKS = [
    ("sh601949", "中国出版", "涨停5.83封板?"),
    ("sh600051", "宁波联合", "昨收破MA12 6.36→该卖"),
    ("sz000900", "现代投资", "14:45定: <=3.68卖"),
    ("sz000630", "铜陵有色", "留100股 防线6.30"),
    ("sh600218", "全柴动力", "MA12 7.65"),
    ("sz000089", "深圳机场", "MA12 6.52"),
    ("sh600261", "阳光照明", "MA12 3.20"),
    ("sh600202", "哈空调", "MA12 5.11"),
]

db = sqlite3.connect(r"d:\vibecoding\stock\backend\data\stock.db")
adv, dec, tot, t_snap = db.execute(
    "SELECT SUM(pct_change>0), SUM(pct_change<0), COUNT(*), MAX(updated_at) "
    "FROM realtime_snapshot WHERE volume>0").fetchone()
db.close()

r = requests.get(
    "https://hq.sinajs.cn/list=" + ",".join(s for s, *_ in STOCKS),
    headers={"User-Agent": "Mozilla/5.0",
             "Referer": "https://finance.sina.com.cn"}, timeout=10)
r.encoding = "gbk"
lines = [f"广度快照 {t_snap}: 涨{adv}/跌{dec}/{tot} ({adv/tot*100:.0f}%)", ""]
notes = {name: note for _, name, note in STOCKS}
for m in re.finditer(r'hq_str_(\w+)="([^"]+)"', r.text):
    f = m.group(2).split(",")
    name = f[0]
    price, pre = float(f[3]), float(f[2])
    pct = (price / pre - 1) * 100 if pre else 0
    hi, lo = float(f[4]), float(f[5])
    lines.append(f"{name}: {price:.2f} ({pct:+.2f}%) 高{hi:.2f}/低{lo:.2f} "
                 f"@{f[31]} | {notes.get(name,'')}")

with io.open(r"d:\vibecoding\stock\pm_check.txt", "w", encoding="utf-8") as fp:
    fp.write("\n".join(lines))
print("saved")

# 反查: 用全市场快照按 名称关键字+价格 匹配用户实际持仓
import io
import sqlite3
import requests
import re

db = sqlite3.connect(r"d:\vibecoding\stock\backend\data\stock.db")
out = io.open(r"d:\vibecoding\stock\find_codes.txt", "w", encoding="utf-8")

# 目标: (截图名称, 截图成本, 截图现价)
targets = [
    ("哈空调", 8.32, 8.27),
    ("山东路桥", 8.47, 8.40),
    ("中国出版", 7.63, 7.57),
]

for name, cost, cur in targets:
    out.write(f"\n== 目标: {name} (成本{cost} 现价{cur}) ==\n")
    # 1. 名称包含关键字的所有股票
    key = name[1:]  # 去掉首字, 如"空调"/"东路桥"/"国出版"
    rows = db.execute(
        "SELECT code, name, price, pct_change FROM realtime_snapshot "
        "WHERE name LIKE ? ORDER BY ABS(price-?) LIMIT 8",
        (f"%{key}%", cur)).fetchall()
    out.write(f"-- 按名称'{key}'匹配 --\n")
    for r in rows:
        out.write(f"   {r[0]} {r[1]} 现价{r[2]} ({r[3]:+.2f}%)\n")
    # 2. 价格贴近(±3%)的全部股票
    rows2 = db.execute(
        "SELECT code, name, price, pct_change FROM realtime_snapshot "
        "WHERE price BETWEEN ? AND ? ORDER BY price LIMIT 20",
        (cur * 0.97, cur * 1.03)).fetchall()
    out.write(f"-- 按价格 {cur*0.97:.2f}~{cur*1.03:.2f} 匹配 --\n")
    for r in rows2:
        out.write(f"   {r[0]} {r[1]} 现价{r[2]} ({r[3]:+.2f}%)\n")

# 3. 创业板候选: 中国出版 sz300788 (不在本地主板库, 直连新浪)
r = requests.get("https://hq.sinajs.cn/list=sz300788", headers={
    "User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"},
    timeout=8)
r.encoding = "gbk"
m = re.match(r'var hq_str_sz300788="(.*)";', r.text.strip())
if m and m.group(1):
    f = m.group(1).split(",")
    out.write(f"\n创业板 300788: {f[0]} 现价 {f[3]} 昨收 {f[2]}\n")

db.close()
out.close()
print("done")

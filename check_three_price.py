import io
import sqlite3

db = sqlite3.connect(r"d:\vibecoding\stock\backend\data\stock.db")
out = io.open(r"d:\vibecoding\stock\check_three_price.txt", "w", encoding="utf-8")
for code, name in [("600893", "哈空调"), ("000498", "山东路桥"),
                   ("601949", "中国出版"), ("600218", "全柴动力")]:
    rows = db.execute(
        "SELECT date, close FROM daily_kline WHERE code=? "
        "ORDER BY date DESC LIMIT 3", (code,)).fetchall()
    snap = db.execute(
        "SELECT name, price, pct_change, updated_at FROM realtime_snapshot "
        "WHERE code=?", (code,)).fetchone()
    out.write(f"{name} {code}: 日线最近3收 {[(r[0], r[1]) for r in rows]}\n")
    out.write(f"   快照: {tuple(snap) if snap else None}\n")
db.close()
out.close()
print("done")

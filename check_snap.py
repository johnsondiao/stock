import sqlite3
db = sqlite3.connect(r"d:\vibecoding\stock\backend\data\stock.db")
n = db.execute("SELECT COUNT(*) FROM realtime_snapshot").fetchone()[0]
t = db.execute("SELECT MAX(updated_at) FROM realtime_snapshot").fetchone()[0]
print(f"realtime_snapshot: {n} 行, updated_at={t}")
n2 = db.execute("SELECT COUNT(*) FROM fundamental").fetchone()[0]
print(f"fundamental: {n2} 行")
db.close()

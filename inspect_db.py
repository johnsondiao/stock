# 探查数据库结构: 表、列、行数、时间范围
import sqlite3

db = sqlite3.connect(r'd:\vibecoding\stock\backend\data\stock.db')
cur = db.cursor()

tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print("tables:", tables)

for t in tables:
    cols = [r[1] for r in cur.execute(f"PRAGMA table_info({t})")]
    n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"\n== {t}: {n} rows, cols={cols}")
    if 'date' in cols:
        lo, hi = cur.execute(f"SELECT MIN(date), MAX(date) FROM {t}").fetchone()
        codes = cur.execute(f"SELECT COUNT(DISTINCT code) FROM {t}").fetchone()[0]
        print(f"   date range: {lo} ~ {hi}, distinct codes: {codes}")
    elif 'code' in cols:
        codes = cur.execute(f"SELECT COUNT(DISTINCT code) FROM {t}").fetchone()[0]
        print(f"   distinct codes: {codes}")
        # 抽样看几行
        for r in cur.execute(f"SELECT * FROM {t} LIMIT 3"):
            print("   sample:", r)

db.close()

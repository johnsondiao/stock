import pandas as pd
import sqlite3

m = pd.read_csv(r"d:\vibecoding\stock\industry_map.csv", encoding="utf-8-sig", dtype=str)
print("映射行数:", len(m), " 板块数:", m["sector"].nunique())
print(m.groupby("sector").size().sort_values(ascending=False).head(10).to_string())

db = sqlite3.connect(r"d:\vibecoding\stock\backend\data\stock.db")
codes_db = {r[0] for r in db.execute("SELECT DISTINCT code FROM daily_kline")}
db.close()
mapped = codes_db & set(m["code"])
print(f"\nDB 股票 {len(codes_db)} 只, 命中行业映射 {len(mapped)} 只, 覆盖率 {len(mapped)/len(codes_db)*100:.1f}%")

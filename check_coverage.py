# 检查数据覆盖度 + akshare 行业分类可用性
import sqlite3

db = sqlite3.connect(r'd:\vibecoding\stock\backend\data\stock.db')
cur = db.cursor()

print("== 5分钟K线 按年统计 ==")
for r in cur.execute("SELECT substr(date,1,4) y, COUNT(*), COUNT(DISTINCT code) FROM kline_5min GROUP BY y ORDER BY y"):
    print(r)

print("\n== 小时K线 按年统计 ==")
for r in cur.execute("SELECT substr(date,1,4) y, COUNT(*), COUNT(DISTINCT code) FROM hourly_kline GROUP BY y ORDER BY y"):
    print(r)

print("\n== 日线 按年统计 ==")
for r in cur.execute("SELECT substr(date,1,4) y, COUNT(*), COUNT(DISTINCT code) FROM daily_kline GROUP BY y ORDER BY y"):
    print(r)
db.close()

# akshare 行业板块
print("\n== 尝试 akshare 行业分类 ==")
try:
    import akshare as ak
    board = ak.stock_board_industry_name_em()
    print("行业板块数:", len(board))
    print(board.head(3))
    cons = ak.stock_board_industry_cons_em(symbol=board.iloc[0]["板块名称"])
    print("第一个板块成分股数:", len(cons), "列:", list(cons.columns)[:8])
except Exception as e:
    print("akshare 失败:", type(e).__name__, e)

# 查证三只股票: 历史价格轨迹 + 疑似除权日(单日跌幅>15%)
import io
import sqlite3

db = sqlite3.connect(r"d:\vibecoding\stock\backend\data\stock.db")
out = io.open(r"d:\vibecoding\stock\ex_rights_check.txt", "w", encoding="utf-8")

targets = [
    ("600202", "哈空调", 8.27),
    ("000498", "山东路桥", 8.40),
    ("601949", "中国出版", 7.57),
]

for code, name, broker_price in targets:
    out.write(f"\n== {name} {code} (券商显示现价 {broker_price}) ==\n")
    rows = db.execute(
        "SELECT date, close FROM daily_kline WHERE code=? "
        "ORDER BY date DESC LIMIT 250", (code,)).fetchall()
    closes = [(r[0][:10], r[1]) for r in rows]
    # 券商价格最接近的历史日期
    best = min(closes, key=lambda x: abs(x[1] - broker_price))
    out.write(f"最接近券商价的历史收盘: {best[0]} = {best[1]}\n")
    # 最近60日价格轨迹(每5日采样)
    out.write("近60交易日轨迹(采样):\n")
    for d, c in closes[:60:5]:
        out.write(f"   {d}: {c}\n")
    # 单日跌幅>12%的疑似除权日(近一年)
    out.write("疑似除权日(单日变动>12%):\n")
    for i in range(len(closes) - 1):
        d1, c1 = closes[i + 1]  # 前一日(列表倒序)
        d2, c2 = closes[i]
        if c1 > 0:
            chg = (c2 / c1 - 1) * 100
            if abs(chg) > 12:
                out.write(f"   {d1} {c1} → {d2} {c2} ({chg:+.1f}%)\n")

db.close()
out.close()
print("done")

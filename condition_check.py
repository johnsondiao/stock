# 昨日条件单复核: 驰宏(收回MA60?) 现代投资(守3.68?) 宁波联合(守6.36?) + 铜陵(守6.30?)
import io
import requests
import pandas as pd

CHECK = [
    ("sh600497", "驰宏锌锗", 10.11, "收盘需站回MA60, 否则清仓"),
    ("sz000900", "现代投资", 3.68, "收盘需守住MA12"),
    ("sh600051", "宁波联合", 6.36, "收盘需守住MA12"),
    ("sz000630", "铜陵有色", 6.30, "留仓最后防线"),
    ("sh600202", "哈空调", 5.10, "收盘需守住MA12"),
    ("sh600261", "阳光照明", 3.20, "收盘需守住MA12"),
]
HEAD = {"User-Agent": "Mozilla/5.0",
        "Referer": "https://finance.sina.com.cn"}

lines = []
for sym, name, level, rule in CHECK:
    u = ("https://quotes.sina.cn/cn/api/json_v2.php/"
         f"CN_MarketDataService.getKLineData?symbol={sym}"
         "&scale=240&ma=no&datalen=70")
    data = requests.get(u, headers=HEAD, timeout=10).json()
    df = pd.DataFrame(data)
    df["close"] = df["close"].astype(float)
    today = df.iloc[-1]
    d = str(today["day"])
    close = today["close"]
    ok = "✅守住" if close > level else "❌跌破"
    lines.append(f"{name}: {d} 收盘 {close:.2f} vs 关键位 {level} → {ok} ({rule})")

with io.open(r"d:\vibecoding\stock\condition_check.txt", "w",
             encoding="utf-8") as f:
    f.write("\n".join(lines))
print("saved")

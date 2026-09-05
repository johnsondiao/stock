# 9/3收盘口径: 剩余持仓的 MA12/MA60 精确位 + 明日执行线
import io
import time
import requests
import pandas as pd

STOCKS = [
    ("sh600218", "全柴动力", "300股 成本7.787"),
    ("sz000089", "深圳机场", "100股 成本6.59"),
    ("sh601949", "中国出版", "100股 成本5.37"),
    ("sh600261", "阳光照明", "100股 成本3.31"),
    ("sh600202", "哈空调",   "100股 成本5.23"),
    ("sz000630", "铜陵有色", "200股 成本6.775"),
]
HEAD = {"User-Agent": "Mozilla/5.0",
        "Referer": "https://finance.sina.com.cn"}

lines = []
for sym, name, pos in STOCKS:
    u = ("https://quotes.sina.cn/cn/api/json_v2.php/"
         f"CN_MarketDataService.getKLineData?symbol={sym}"
         "&scale=240&ma=no&datalen=80")
    data = requests.get(u, headers=HEAD, timeout=10).json()
    df = pd.DataFrame(data)
    df["close"] = df["close"].astype(float)
    ma12 = df["close"].rolling(12).mean().iloc[-1]
    ma60 = df["close"].rolling(60).mean().iloc[-1]
    last = df.iloc[-1]
    bull = ma12 > ma60
    lines.append(f"{name} [{pos}]: {last['day']} 收 {last['close']:.2f} | "
                 f"MA12={ma12:.3f} MA60={ma60:.3f} "
                 f"({'多头' if bull else '空头'}) | "
                 f"收盘在MA12{'上' if last['close'] > ma12 else '下'}")
    time.sleep(0.4)

with io.open(r"d:\vibecoding\stock\levels_tomorrow.txt", "w",
             encoding="utf-8") as f:
    f.write("\n".join(lines))
print("saved")

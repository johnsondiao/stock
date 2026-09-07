# 9/7 收盘定档口径: 新浪scale=240末根仍是上一交易日时, 并入今日实时收盘价重算MA12/MA60
import io
import re
import time
import requests
import pandas as pd

TODAY = pd.Timestamp.now().strftime("%Y-%m-%d")
STOCKS = [
    ("sh601949", "中国出版", "100股 成本5.37"),
    ("sh600218", "全柴动力", "500股 成本7.78"),
    ("sz000089", "深圳机场", "300股 成本6.651"),
    ("sh600261", "阳光照明", "100股 成本3.31"),
    ("sh600202", "哈空调",   "100股 成本5.23"),
    ("sz000630", "铜陵有色", "100股 摊薄7.154"),
]
HEAD = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"}


def get(url, tries=4, enc=None):
    for i in range(tries):
        try:
            r = requests.get(url, headers=HEAD, timeout=12)
            if enc:
                r.encoding = enc
            return r
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(1.0 + i)


# 今日实时/收盘价（hq.sinajs.cn, f[3]=现价, 15:00后即收盘价）
rt = get("https://hq.sinajs.cn/list=" + ",".join(s for s, *_ in STOCKS), enc="gbk")
close_today = {}
for m in re.finditer(r'hq_str_(\w+)="([^"]+)"', rt.text):
    f = m.group(2).split(",")
    close_today[f[0]] = float(f[3])  # 按中文名索引

lines = [f"今日收盘口径 MA (TODAY={TODAY})", ""]
for sym, name, pos in STOCKS:
    u = ("https://quotes.sina.cn/cn/api/json_v2.php/"
         f"CN_MarketDataService.getKLineData?symbol={sym}"
         "&scale=240&ma=no&datalen=80")
    data = get(u).json()
    df = pd.DataFrame(data)
    df["close"] = df["close"].astype(float)
    last_day = df.iloc[-1]["day"]
    px = close_today.get(name)
    appended = False
    # 若新浪末根不是今日, 用今日收盘价补一根（真正的今日收盘口径）
    if str(last_day)[:10] != TODAY and px is not None:
        df = pd.concat([df, pd.DataFrame([{"day": TODAY, "close": px}])],
                       ignore_index=True)
        appended = True
    ma12 = df["close"].rolling(12).mean().iloc[-1]
    ma60 = df["close"].rolling(60).mean().iloc[-1]
    last = df.iloc[-1]
    close = float(last["close"])
    bull = ma12 > ma60
    above = close > ma12
    tag = "补今日收盘" if appended else f"新浪已含{last_day}"
    lines.append(
        f"{name} [{pos}]: 收 {close:.3f} ({tag}) | "
        f"MA12={ma12:.3f} MA60={ma60:.3f} ({'多头' if bull else '空头'}) | "
        f"收盘在MA12{'上' if above else '下'} | 距MA12 {(close/ma12-1)*100:+.2f}%")
    time.sleep(0.4)

with io.open(r"d:\vibecoding\stock\levels_close_today.txt", "w",
             encoding="utf-8") as f:
    f.write("\n".join(lines))
print("saved")

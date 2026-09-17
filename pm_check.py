# 9/8 早盘核查: 广度 + 持仓实时价 + 昨收口径MA12/MA60 + 纪律线
import io
import re
import sqlite3
import time
import requests
import pandas as pd

# 2026-09-17 09:44 深圳机场100股已清仓(卖价6.48, 实亏-69.07), 空仓状态, 移入WATCH跟踪
STOCKS = [
]
# 2026-09-15 11:04 全柴动力300股已卖出(实亏-157.07), 移入WATCH仅跟踪
WATCH = ["sh601949", "sz000630", "sh600116", "sh600261", "sh600202", "sh600218", "sz000089"]
# 已清仓但继续跟踪(不参与纪律判定)
HEAD = {"User-Agent": "Mozilla/5.0",
        "Referer": "https://finance.sina.com.cn"}

# 1) 昨收口径 MA12/MA60（新浪 scale=240 日线 rolling，过滤盘中bar）
today = pd.Timestamp.now().strftime("%Y-%m-%d")
ma_map = {}
for sym in [s for s, *_ in STOCKS] + WATCH:
    try:
        u = ("https://quotes.sina.cn/cn/api/json_v2.php/"
             f"CN_MarketDataService.getKLineData?symbol={sym}"
             "&scale=240&ma=no&datalen=80")
        data = requests.get(u, headers=HEAD, timeout=10).json()
        df = pd.DataFrame(data)
        df["close"] = df["close"].astype(float)
        df = df[df["day"] < today]  # 盘中形成bar不参与昨收口径
        ma12 = df["close"].rolling(12).mean().iloc[-1]
        ma60 = df["close"].rolling(60).mean().iloc[-1]
        last = df.iloc[-1]
        ma_map[sym] = (ma12, ma60, last["day"], float(last["close"]))
    except Exception as e:
        ma_map[sym] = None
        print(f"{sym} MA计算失败: {e}")
    time.sleep(0.4)

# 2) 广度快照
db = sqlite3.connect(r"d:\vibecoding\stock\backend\data\stock.db")
adv, dec, tot, t_snap = db.execute(
    "SELECT SUM(pct_change>0), SUM(pct_change<0), COUNT(*), MAX(updated_at) "
    "FROM realtime_snapshot WHERE volume>0").fetchone()
db.close()

# 3) 实时行情
r = requests.get(
    "https://hq.sinajs.cn/list="
    + ",".join([s for s, *_ in STOCKS] + WATCH),
    headers=HEAD, timeout=10)
r.encoding = "gbk"
lines = [f"广度快照 {t_snap}: 涨{adv}/跌{dec}/{tot} ({adv/tot*100:.0f}%)", ""]
notes = {name: note for _, name, note in STOCKS}
for m in re.finditer(r'hq_str_(\w+)="([^"]+)"', r.text):
    f = m.group(2).split(",")
    name = f[0]
    price, pre = float(f[3]), float(f[2])
    pct = (price / pre - 1) * 100 if pre else 0
    hi, lo = float(f[4]), float(f[5])
    held = name in notes
    ma = ma_map.get(m.group(1))
    if ma:
        ma12, ma60, ma_day, ma_close = ma
        bull = "多头" if ma12 > ma60 else "空头"
        pos = "上" if price > ma12 else "下"
        ma_txt = (f"MA12={ma12:.3f} MA60={ma60:.3f}({bull},{ma_day}收{ma_close:.2f})"
                  f" 现价在MA12{pos}")
    else:
        ma_txt = "MA数据缺失"
    tag = "" if held else "  [已清仓·仅跟踪]"
    disc = notes.get(name, "") if held else ""
    lines.append(f"{name}{tag}: {price:.2f} ({pct:+.2f}%) 高{hi:.2f}/低{lo:.2f} "
                 f"@{f[31]}\n  {ma_txt}"
                 + (f"\n  纪律: {disc}" if disc else ""))

with io.open(r"d:\vibecoding\stock\pm_check.txt", "w", encoding="utf-8") as fp:
    fp.write("\n".join(lines))
print("saved")

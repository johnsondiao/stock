# 三只股票完整体检: 日线/小时/5分钟三周期 + ma_combo 闸门判定
# 科新机电300092(创业板,不在本地库) / 粤传媒002181 / 福达合金603045
import io
import re
import time
import requests
import pandas as pd

STOCKS = [
    ("sz300092", "科新机电", "创业板"),
    ("sz002181", "粤传媒", None),
    ("sh603045", "福达合金", None),
]
HEAD = {"User-Agent": "Mozilla/5.0",
        "Referer": "https://finance.sina.com.cn"}

ind = pd.read_csv(r"d:\vibecoding\stock\industry_map.csv",
                  encoding="utf-8-sig", dtype=str)
code2sec = dict(zip(ind["code"], ind["sector"]))


def get_kline(sym, scale, n):
    u = ("https://quotes.sina.cn/cn/api/json_v2.php/"
         f"CN_MarketDataService.getKLineData?symbol={sym}"
         f"&scale={scale}&ma=no&datalen={n}")
    for _ in range(3):
        try:
            data = requests.get(u, headers=HEAD, timeout=10).json()
            df = pd.DataFrame(data)
            df["close"] = df["close"].astype(float)
            return df
        except Exception:
            time.sleep(2)
    return None


def realtime(sym):
    r = requests.get(f"https://hq.sinajs.cn/list={sym}", headers=HEAD,
                     timeout=8)
    r.encoding = "gbk"
    m = re.search(r'"([^"]+)"', r.text)
    if not m:
        return None
    f = m.group(1).split(",")
    price, pre = float(f[3]), float(f[2])
    return {"price": price, "pct": (price / pre - 1) * 100 if pre else 0,
            "time": f[31], "date": f[30]}


def bars_since_cross(df, fast, slow):
    """金叉后经过根数; None=窗口内无金叉; 负数=当前空头"""
    maf = df["close"].rolling(fast).mean()
    mas = df["close"].rolling(slow).mean()
    bull = maf.iloc[-1] > mas.iloc[-1]
    above = df["close"].iloc[-1] > maf.iloc[-1] and df["close"].iloc[-1] > mas.iloc[-1]
    cross = (maf > mas) & (maf <= mas).shift(1, fill_value=False)
    cross = cross & maf.notna() & mas.notna()
    ago = None
    if cross.any():
        ago = len(df) - 1 - df.index[cross][-1]
    return bull, above, ago, maf.iloc[-1], mas.iloc[-1]


out = io.open(r"d:\vibecoding\stock\three_check.txt", "w", encoding="utf-8")
for sym, name, note in STOCKS:
    code = sym[2:]
    sec = code2sec.get(code, note or "未分类")
    q = realtime(sym)
    out.write(f"\n===== {name} {code} [{sec}] =====\n")
    if q:
        out.write(f"实时: {q['price']} ({q['pct']:+.2f}%) @{q['date']} {q['time']}\n")

    # 日线 12/60 (闸门C)
    d = get_kline(sym, 240, 300)
    if d is not None and len(d) > 62:
        bull, above, ago, maf, mas = bars_since_cross(d, 12, 60)
        chg5 = (d["close"].iloc[-1] / d["close"].iloc[-6] - 1) * 100
        chg20 = (d["close"].iloc[-1] / d["close"].iloc[-21] - 1) * 100
        gate_c = "✓通过" if (bull and maf > mas) else "✗不过"
        out.write(f"日线: {'多头' if bull else '空头'} MA12={maf:.2f}/MA60={mas:.2f} "
                  f"{'价在线上' if above else '价在均线下'} "
                  f"金叉距今{ago}日 | 闸门C(MA12>MA60): {gate_c}\n")
        out.write(f"   近5日{chg5:+.1f}% 近20日{chg20:+.1f}%\n")
        time.sleep(0.5)

    # 小时 24/60 (闸门A+B)
    h = get_kline(sym, 60, 300)
    if h is not None and len(h) > 62:
        bull, above, ago, maf, mas = bars_since_cross(h, 24, 60)
        gate_ab = ("✓通过" if (bull and above and ago is not None and ago < 8)
                   else "✗不过")
        out.write(f"小时: {'多头' if bull else '空头'} MA24={maf:.2f}/MA60={mas:.2f} "
                  f"{'价在线上' if above else '价破均线'} "
                  f"金叉距今{ago}根 | 闸门A+B(站上+金叉8根内): {gate_ab}\n")
        time.sleep(0.5)

    # 5分钟 12/288 (入场)
    f5 = get_kline(sym, 5, 400)
    if f5 is not None and len(f5) > 290:
        bull, above, ago, maf, mas = bars_since_cross(f5, 12, 288)
        entry = ("✓触发" if (bull and ago is not None and ago < 48)
                 else "✗未触发")
        out.write(f"5分钟: {'多头' if bull else '空头'} MA12={maf:.3f}/MA288={mas:.3f} "
                  f"{'价在线上' if above else '价破均线'} "
                  f"金叉距今{ago}根 | 入场(金叉48根内): {entry}\n")
    else:
        out.write("5分钟: 数据不足\n")

    # 综合判定
    verdict = []
    if d is not None and len(d) > 62:
        bd = bars_since_cross(d, 12, 60)
        if not bd[0]:
            verdict.append("日线趋势未确认")
    if h is not None and len(h) > 62:
        bh = bars_since_cross(h, 24, 60)
        if not (bh[0] and bh[1] and bh[2] is not None and bh[2] < 8):
            verdict.append("小时闸门未过")
    if f5 is not None and len(f5) > 290:
        b5 = bars_since_cross(f5, 12, 288)
        if not (b5[0] and b5[2] is not None and b5[2] < 48):
            verdict.append("5分入场未触发")
    out.write(f"ma_combo综合: {'全部通过→会被系统选中' if not verdict else '不通过: ' + '、'.join(verdict)}\n")

out.close()
print("saved three_check.txt")

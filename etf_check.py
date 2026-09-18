# -*- coding: utf-8 -*-
"""ETF 轮动观察清单 (2026-09-18 新增)

逻辑与个股体系对齐:
- 趋势状态: 现价 vs MA12 / MA60 (昨收口径, 同 pm_check)
- 动量: 5日/20日涨幅
- 排序: 5日涨幅降序, 多头排列优先
用法: python etf_check.py   (约22次K线请求, quotes.sina.cn 域, 与 vip.stock 分开限流)
"""
import json
import time
import requests

# 全局限流器之外的轻量节流(保守起见)
SLEEP = 1.0

ETF_POOL = [
    # (代码, 名称, 分类)
    ("sh510300", "沪深300ETF", "宽基"),
    ("sh510500", "中证500ETF", "宽基"),
    ("sh512100", "中证1000ETF", "宽基"),
    ("sz159915", "创业板ETF", "宽基"),
    ("sh588000", "科创50ETF", "宽基"),
    ("sh512480", "半导体ETF", "科技"),
    ("sh512760", "芯片ETF", "科技"),
    ("sh515980", "人工智能ETF", "科技"),
    ("sh515050", "5G通信ETF", "科技"),
    ("sh512980", "传媒ETF", "科技"),
    ("sh512010", "医药ETF", "医药"),
    ("sh512690", "酒ETF", "消费"),
    ("sh515030", "新能源车ETF", "制造"),
    ("sh515790", "光伏ETF", "制造"),
    ("sh512660", "军工ETF", "制造"),
    ("sh512400", "有色金属ETF", "资源"),
    ("sh515220", "煤炭ETF", "资源"),
    ("sz159611", "电力ETF", "公用"),
    ("sh512800", "银行ETF", "金融"),
    ("sh512880", "证券ETF", "金融"),
    ("sh512200", "房地产ETF", "金融"),
]

HEAD = {"User-Agent": "Mozilla/5.0",
        "Referer": "https://finance.sina.com.cn"}


def fetch_quotes(codes):
    """批量实时行情 -> {code: (name, price, prev_close)}"""
    url = "https://hq.sinajs.cn/list=" + ",".join(codes)
    r = requests.get(url, headers=HEAD, timeout=10)
    r.encoding = "gbk"
    out = {}
    for line in r.text.strip().split("\n"):
        if '="' not in line:
            continue
        sym = line.split("=")[0].split("_")[-1]
        f = line.split('"')[1].split(",")
        if len(f) > 4:
            out[sym] = (f[0], float(f[3]), float(f[2]))  # 名称, 现价, 昨收
    return out


def fetch_daily(sym, datalen=80):
    """日线K线(昨收口径) -> list[dict]"""
    u = ("https://quotes.sina.cn/cn/api/json_v2.php/"
         f"CN_MarketDataService.getKLineData?symbol={sym}"
         f"&scale=240&ma=no&datalen={datalen}")
    r = requests.get(u, headers=HEAD, timeout=10)
    data = r.json()
    if isinstance(data, dict):
        return []
    import datetime
    today = datetime.date.today().strftime("%Y-%m-%d")
    return [d for d in data if d["day"] < today]  # 排除盘中bar


def main():
    codes = [c for c, _, _ in ETF_POOL]
    names = {c: n for c, n, _ in ETF_POOL}
    cats = {c: t for c, _, t in ETF_POOL}

    quotes = fetch_quotes(codes)
    rows = []
    for code in codes:
        try:
            k = fetch_daily(code)
            closes = [float(d["close"]) for d in k]
            if len(closes) < 15:
                continue
            ma12 = sum(closes[-12:]) / 12
            ma60 = sum(closes[-60:]) / 60 if len(closes) >= 60 else None
            c5 = closes[-1] / closes[-6] - 1 if len(closes) >= 6 else None
            c20 = closes[-1] / closes[-21] - 1 if len(closes) >= 21 else None
            q = quotes.get(code)
            price = q[1] if q else closes[-1]
            prev = q[2] if q else closes[-1]
            today_pct = price / prev - 1 if q else None
            # 趋势状态
            if price > ma12 and ma12 > (ma60 or 0):
                state = "多头"
            elif price > ma12:
                state = "反弹"
            else:
                state = "走弱"
            rows.append({
                "code": code, "name": names[code], "cat": cats[code],
                "price": price, "today": today_pct, "ret5": c5, "ret20": c20,
                "ma12": ma12, "ma60": ma60, "state": state,
            })
            time.sleep(SLEEP)
        except Exception as e:
            print(f"  [warn] {code} {names[code]} 失败: {e}")
            time.sleep(SLEEP)

    # 排序: 多头优先, 再按5日涨幅
    order = {"多头": 0, "反弹": 1, "走弱": 2}
    rows.sort(key=lambda r: (order[r["state"]], -(r["ret5"] or -9)))

    print(f"\n{'状态':<4} {'名称':<12} {'分类':<4} {'现价':>7} {'今日':>7} "
          f"{'5日':>7} {'20日':>7} {'MA12':>7} {'MA60':>7}")
    print("-" * 78)
    for r in rows:
        print(f"{r['state']:<4} {r['name']:<12} {r['cat']:<4} {r['price']:>7.3f} "
              f"{(r['today'] or 0)*100:>6.2f}% {(r['ret5'] or 0)*100:>6.2f}% "
              f"{(r['ret20'] or 0)*100:>6.2f}% {r['ma12']:>7.3f} "
              f"{(r['ma60'] or 0):>7.3f}")

    bull = [r for r in rows if r["state"] == "多头" and (r["ret5"] or 0) > 0]
    print("\n观察池(多头排列且5日涨幅>0):")
    for r in bull:
        print(f"  {r['name']} {r['price']:.3f}  5日{(r['ret5'] or 0)*100:+.2f}%  "
              f"纪律线MA12={r['ma12']:.3f} (收盘跌破次日离场)")

    return rows


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
周末持仓复盘 + 下一交易日执行计划

数据来源: 本地 SQLite 缓存(日线/60分钟/5分钟), 实时价走新浪快照。
输出: 每只持仓的多周期状态、盈亏、以及次日的关键执行价位。

用法:
    python weekend_review.py
"""

import sqlite3
import time

import pandas as pd
import requests

DB = r"d:\vibecoding\stock\backend\data\stock.db"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://finance.sina.com.cn",
}

# (代码, 名称, 成本价, 股数) —— 以 levels_tomorrow.py 口径为准
HOLD = [
    ("600218", "全柴动力", 7.787, 300),
    ("000089", "深圳机场", 6.590, 100),
    ("601949", "中国出版", 5.370, 100),
    ("600261", "阳光照明", 3.310, 100),
    ("600202", "哈空调",   5.230, 100),
    ("000630", "铜陵有色", 6.775, 200),
]

DAILY_FAST, DAILY_SLOW = 12, 60
HOUR_FAST, HOUR_SLOW = 12, 60


def sina_symbol(code: str) -> str:
    return f"sh{code}" if code.startswith(("6", "9")) else f"sz{code}"


def load_kline(code: str, table: str) -> pd.DataFrame:
    conn = sqlite3.connect(DB, timeout=30)
    try:
        df = pd.read_sql_query(
            f"SELECT date, open, high, low, close, volume FROM {table} "
            f"WHERE code=? ORDER BY date", conn, params=(code,))
    finally:
        conn.close()
    if not df.empty:
        df["close"] = df["close"].astype(float)
    return df


def realtime(codes: list[str]) -> dict[str, dict]:
    """新浪批量行情: 返回 code -> {price, open, high, low, pre_close, volume, pct}"""
    syms = [sina_symbol(c) for c in codes]
    r = requests.get(f"https://hq.sinajs.cn/list={','.join(syms)}",
                     headers=HEADERS, timeout=10)
    r.encoding = "gbk"
    out: dict[str, dict] = {}
    for line in r.text.strip().splitlines():
        if '="' not in line:
            continue
        sym = line.split("hq_str_")[1].split('="')[0]
        f = line.split('="')[1].rstrip('";').split(",")
        if len(f) < 32 or not f[0]:
            continue
        pre = float(f[2]) if f[2] else 0
        price = float(f[3]) if f[3] else pre
        out[sym[2:]] = {
            "name": f[0],
            "open": float(f[1]) if f[1] else 0,
            "pre_close": pre,
            "price": price,
            "high": float(f[4]) if f[4] else 0,
            "low": float(f[5]) if f[5] else 0,
            "volume": float(f[8]) / 100 if f[8] else 0,
            "amount": float(f[9]) if f[9] else 0,
            "pct": (price - pre) / pre * 100 if pre else 0,
            "date": f[30],
        }
    return out


def ma(series: pd.Series, n: int) -> float:
    return float(series.rolling(n).mean().iloc[-1]) if len(series) >= n else float("nan")


def main():
    codes = [c for c, *_ in HOLD]
    rt = realtime(codes)

    print("=" * 78)
    print(f"周末持仓复盘 · 数据截至 {time.strftime('%Y-%m-%d %H:%M')}")
    print("=" * 78)

    total_cost = total_mv = 0.0
    rows = []

    for code, name, cost, shares in HOLD:
        d = load_kline(code, "daily_kline")
        h = load_kline(code, "hourly_kline")

        if d.empty:
            print(f"\n{name} {code}: 日线数据缺失, 跳过")
            continue

        last_day = d["date"].iloc[-1][:10]
        d_close = float(d["close"].iloc[-1])
        d_ma12 = ma(d["close"], DAILY_FAST)
        d_ma60 = ma(d["close"], DAILY_SLOW)
        d_bull = d_ma12 > d_ma60

        h_ma12 = ma(h["close"], HOUR_FAST) if len(h) >= HOUR_FAST else float("nan")
        h_ma60 = ma(h["close"], HOUR_SLOW) if len(h) >= HOUR_SLOW else float("nan")
        h_close = float(h["close"].iloc[-1]) if not h.empty else float("nan")
        h_bull = h_ma12 > h_ma60

        q = rt.get(code, {})
        price = q.get("price") or d_close
        pnl_pct = (price - cost) / cost * 100
        pnl_amt = (price - cost) * shares
        total_cost += cost * shares
        total_mv += price * shares

        rows.append({
            "code": code, "name": name, "cost": cost, "shares": shares,
            "price": price, "pnl_pct": pnl_pct, "pnl_amt": pnl_amt,
            "day": last_day, "d_close": d_close,
            "d_ma12": d_ma12, "d_ma60": d_ma60, "d_bull": d_bull,
            "h_close": h_close, "h_ma12": h_ma12, "h_ma60": h_ma60,
            "h_bull": h_bull,
        })

        print(f"\n【{name} {code}】{shares}股  成本 {cost:.3f}")
        print(f"  最新价 {price:.2f}  盈亏 {pnl_pct:+.2f}% ({pnl_amt:+.0f}元)")
        print(f"  日线  截至 {last_day} 收 {d_close:.2f} | "
              f"MA12={d_ma12:.3f} MA60={d_ma60:.3f} "
              f"({'多头' if d_bull else '空头'})")
        print(f"  60分  收 {h_close:.2f} | "
              f"MA12={h_ma12:.3f} MA60={h_ma60:.3f} "
              f"({'多头' if h_bull else '空头'})")

        # ── 次日执行建议 ──
        if d_close >= d_ma12:
            pos = f"收盘在 MA12 上方 (余量 {d_close - d_ma12:+.3f})"
            action = f"持有, 防线 MA12={d_ma12:.2f}; 收盘跌破则减/清"
        else:
            pos = f"收盘在 MA12 下方 (缺口 {d_close - d_ma12:+.3f})"
            if d_bull:
                action = f"警戒: 需重新站回 {d_ma12:.2f}; 否则按纪律减仓"
            else:
                action = f"空头排列且破 MA12, 优先减仓; 最后防线 MA60={d_ma60:.2f}"
        print(f"  状态  {pos}")
        print(f"  执行  {action}")

    # ── 组合总览 ──
    print("\n" + "=" * 78)
    print("组合总览")
    print("=" * 78)
    for r in sorted(rows, key=lambda x: -x["pnl_pct"]):
        flag = "↑" if r["pnl_pct"] >= 0 else "↓"
        bull = "多" if r["d_bull"] else "空"
        safe = "✓" if r["d_close"] >= r["d_ma12"] else "✗"
        print(f"  {flag} {r['name']:<6} {r['shares']:>4}股  "
              f"成本{r['cost']:>6.3f}  现价{r['price']:>6.2f}  "
              f"{r['pnl_pct']:>+7.2f}%  {r['pnl_amt']:>+8.0f}元  "
              f"日线{bull} MA12{safe}")

    if total_cost:
        pnl = total_mv - total_cost
        print(f"\n  总投入 {total_cost:,.0f} 元 | 现值 {total_mv:,.0f} 元 | "
              f"盈亏 {pnl:+,.0f} 元 ({pnl / total_cost * 100:+.2f}%)")

    # ── 次日关注位 ──
    print("\n" + "=" * 78)
    print("次日关键位速查 (收盘价为准)")
    print("=" * 78)
    print(f"  {'名称':<8}{'现价':>8}{'MA12(防线)':>12}{'MA60(底线)':>12}{'距MA12':>10}")
    for r in rows:
        gap = (r["d_close"] - r["d_ma12"]) / r["d_ma12"] * 100
        print(f"  {r['name']:<8}{r['d_close']:>8.2f}{r['d_ma12']:>12.2f}"
              f"{r['d_ma60']:>12.2f}{gap:>9.2f}%")


if __name__ == "__main__":
    main()

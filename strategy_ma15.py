"""策略 ma_atr15: 15分钟线 快MA4 / 慢MA240 / 过滤MA960 + ATR(300)

原始(通达信)逻辑:
    快:MA(C,4); 慢:MA(C,240); 过滤:MA(C,960)
    TRVAL:=MAX(MAX((HIGH-LOW),ABS(REF(CLOSE,1)-HIGH)),ABS(REF(CLOSE,1)-LOW))
    atr:=MA(TRVAL,300)
    买入: CROSSUP(快,慢) AND 慢>过滤
    卖出: CROSSDOWN(快,慢) AND 慢<过滤
    DRAWNUMBER 标注位: 买 → 慢+atr*{1,3,5,7} / C / 慢-atr
                      卖 → 慢-atr*{1,3,5,7} / C / 慢+atr

本脚本做两件事:
    1. scan   —— 全市场扫描当前(近期)买入信号, 输出标注价位
    2. backtest —— 用可用历史区间统计信号后 1/3/5 个交易日的胜率与盈亏比

用法:
    python strategy_ma15.py scan
    python strategy_ma15.py backtest
    python strategy_ma15.py scan 600218 000089     # 只看指定股票
"""
import io
import sqlite3
import sys
import time

import numpy as np
import pandas as pd

DB = r"d:\vibecoding\stock\backend\data\stock.db"
MAP = r"d:\vibecoding\stock\industry_map.csv"

FAST, SLOW, FILT, ATR_N = 4, 240, 960, 300
BARS_PER_DAY = 16          # A股一天 16 根 15 分钟 K 线
FWD = {"1日": 16, "3日": 48, "5日": 80}


def load_names():
    try:
        ind = pd.read_csv(MAP, encoding="utf-8-sig", dtype=str)
        return dict(zip(ind["code"], ind["name"])), dict(zip(ind["code"], ind["sector"]))
    except Exception:
        return {}, {}


def calc(df: pd.DataFrame) -> pd.DataFrame:
    """df 需含 open/high/low/close, 按 date 升序"""
    c = df["close"].astype(float)
    h = df["high"].astype(float)
    lo = df["low"].astype(float)
    d = pd.DataFrame({"close": c})
    d["fast"] = c.rolling(FAST).mean()
    d["slow"] = c.rolling(SLOW).mean()
    d["filt"] = c.rolling(FILT).mean()

    prevc = c.shift(1)
    tr = pd.concat([h - lo, (prevc - h).abs(), (prevc - lo).abs()], axis=1).max(axis=1)
    d["atr"] = tr.rolling(ATR_N).mean()

    up = (d["fast"] > d["slow"]) & (d["fast"].shift(1) <= d["slow"].shift(1))
    dn = (d["fast"] < d["slow"]) & (d["fast"].shift(1) >= d["slow"].shift(1))
    d["buy"] = up & (d["slow"] > d["filt"])
    d["sell"] = dn & (d["slow"] < d["filt"])
    return d


def iter_codes(codes, chunk=80):
    """分批读取 15 分钟数据, 减少内存峰值"""
    db = sqlite3.connect(DB, timeout=60)
    for i in range(0, len(codes), chunk):
        part = codes[i:i + chunk]
        ph = ",".join("?" * len(part))
        q = (f"SELECT code,date,open,high,low,close FROM kline_15min "
             f"WHERE code IN ({ph}) ORDER BY code,date")
        df = pd.read_sql_query(q, db, params=part)
        if df.empty:
            continue
        yield df
    db.close()


def get_codes():
    db = sqlite3.connect(DB, timeout=60)
    codes = [r[0] for r in db.execute(
        "SELECT DISTINCT code FROM kline_15min").fetchall()]
    db.close()
    return codes


def do_scan(only=None):
    codes = only or get_codes()
    names, secs = load_names()
    out = []
    t0 = time.time()
    done = 0
    for df in iter_codes(codes):
        for code, g in df.groupby("code", sort=False):
            done += 1
            if len(g) < FILT + 5:
                continue
            d = calc(g.reset_index(drop=True))
            sig = d["buy"].values
            idx = np.flatnonzero(sig)
            if len(idx) == 0:
                continue
            last = idx[-1]
            bars_ago = len(d) - 1 - last
            if bars_ago > BARS_PER_DAY * 2:      # 只看 2 个交易日内
                continue
            r = d.iloc[last]
            cur = float(d["close"].iloc[-1])
            atr = float(r["atr"]) if pd.notna(r["atr"]) else float("nan")
            slow = float(r["slow"])
            filt = float(r["filt"])
            sig_gap = (float(r["close"]) / slow - 1) * 100    # 信号时距慢线
            trend = (slow / filt - 1) * 100                   # 慢>滤幅度
            out.append({
                "code": code, "name": names.get(code, ""), "sector": secs.get(code, ""),
                "price": cur, "bars_ago": bars_ago, "slow": slow,
                "filt": filt, "atr": atr,
                "gap": sig_gap, "trend": trend,
                "atrp": atr / cur * 100 if atr == atr else float("nan"),
                "t1": slow + atr, "t3": slow + atr * 3,
                "t5": slow + atr * 5, "t7": slow + atr * 7,
                "stop": slow - atr,
            })
    print(f"扫描 {done} 只, 耗时 {time.time()-t0:.0f}s")
    return pd.DataFrame(out)


def load_bench():
    """日线基准: 每个交易日, 全市场未来 1/3/5 日收益的中位数

    没有基准就无法判断策略是真有效还是搭了市场顺风车。
    """
    db = sqlite3.connect(DB, timeout=60)
    d = pd.read_sql_query(
        "SELECT code, substr(date,1,10) d, close FROM daily_kline "
        "WHERE date>='2026-04-01' ORDER BY code,date", db)
    db.close()
    d = d.sort_values(["code", "d"])
    g = d.groupby("code")["close"]
    for k, n in [("1日", 1), ("3日", 3), ("5日", 5)]:
        d["fwd" + k] = (g.shift(-n) / d["close"] - 1) * 100
    return d.groupby("d")[["fwd1日", "fwd3日", "fwd5日"]].median()


def do_backtest(only=None):
    codes = only or get_codes()
    recs = []
    t0 = time.time()
    done = 0
    for df in iter_codes(codes):
        for code, g in df.groupby("code", sort=False):
            done += 1
            if len(g) < FILT + 5:
                continue
            g = g.reset_index(drop=True)
            d = calc(g)
            c = d["close"].values
            dates = g["date"].values
            idx = np.flatnonzero(d["buy"].values)
            n = len(c)
            for i in idx:
                row = {"code": code, "date": str(dates[i])[:10]}
                # 信号时的形态特征, 用于分组找"哪类信号才有真 alpha"
                sl = d["slow"].iloc[i]
                fl = d["filt"].iloc[i]
                row["gap"] = (c[i] / sl - 1) * 100 if sl else np.nan      # 距慢线
                row["trend"] = (sl / fl - 1) * 100 if fl else np.nan      # 慢>滤幅度
                row["atrp"] = (d["atr"].iloc[i] / c[i] * 100
                               if pd.notna(d["atr"].iloc[i]) else np.nan)  # ATR%
                ok = False
                for k, b in FWD.items():
                    j = i + b
                    if j < n:
                        row[k] = (c[j] / c[i] - 1) * 100
                        ok = True
                    else:
                        row[k] = np.nan
                if ok:
                    recs.append(row)
    print(f"回测扫描 {done} 只, 信号 {len(recs)} 个, 耗时 {time.time()-t0:.0f}s")
    return pd.DataFrame(recs)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "scan"
    only = sys.argv[2:] if len(sys.argv) > 2 else None

    if mode == "scan":
        res = do_scan(only)
        if res.empty:
            print("\n当前无买入信号 (近 2 个交易日内)")
            return
        res = res.sort_values("bars_ago")
        # 回测验证过的优选条件: 距慢线[-1,1] 且 慢>滤[2,5] 且 非ST 且 ATR<2%
        good = ((res["gap"] >= -1) & (res["gap"] <= 1)
                & (res["trend"] >= 2) & (res["trend"] <= 5)
                & (~res["name"].str.contains("ST", na=False))
                & (res["atrp"] < 2))
        o = io.open(r"d:\vibecoding\stock\ma15_scan.txt", "w", encoding="utf-8")
        w = lambda s="": (print(s), o.write(s + "\n"))
        w(f"ma_atr15 买入信号 · {time.strftime('%Y-%m-%d %H:%M')} · "
          f"命中 {len(res)} 只, 其中优选 {int(good.sum())} 只")
        w("优选条件(回测验证): 信号时距慢线[-1%,+1%] 且 慢>滤[2%,5%] 且 非ST 且 ATR<2%")
        w("=" * 100)
        w("★ 优选池")
        w(f"{'代码':<8}{'名称':<10}{'板块':<8}{'现价':>7}{'几根前':>7}"
          f"{'距慢线':>8}{'慢>滤%':>8}{'ATR%':>7}")
        for _, r in res[good].iterrows():
            w(f"{r['code']:<8}{r['name']:<10}{r['sector']:<8}{r['price']:>7.2f}"
              f"{int(r['bars_ago']):>7}{r['gap']:>+8.2f}{r['trend']:>8.2f}{r['atrp']:>7.2f}")
        w()
        w("=" * 100)
        w("标注价位 (对应原公式 DRAWNUMBER): C / 慢+ATR*{1,3,5,7} / 慢-ATR")
        w(f"{'名称':<10}{'C':>8}{'+1ATR':>9}{'+3ATR':>9}"
          f"{'+5ATR':>9}{'+7ATR':>9}{'-ATR(守)':>10}")
        for _, r in res[good].iterrows():
            w(f"{r['name']:<10}{r['price']:>8.2f}{r['t1']:>9.2f}{r['t3']:>9.2f}"
              f"{r['t5']:>9.2f}{r['t7']:>9.2f}{r['stop']:>10.2f}")
        w()
        w("=" * 100)
        w(f"其余 {int((~good).sum())} 只 (未过优选条件)")
        w(f"{'代码':<8}{'名称':<10}{'板块':<8}{'现价':>7}{'几根前':>7}"
          f"{'距慢线':>8}{'慢>滤%':>8}{'ATR%':>7}")
        for _, r in res[~good].head(120).iterrows():
            w(f"{r['code']:<8}{r['name']:<10}{r['sector']:<8}{r['price']:>7.2f}"
              f"{int(r['bars_ago']):>7}{r['gap']:>+8.2f}{r['trend']:>8.2f}{r['atrp']:>7.2f}")
        o.close()
        print(f"\n命中 {len(res)} 只, 优选 {int(good.sum())} 只 → ma15_scan.txt")

    elif mode == "backtest":
        res = do_backtest(only)
        if res.empty:
            print("无可用信号样本")
            return
        bench = load_bench()
        # 每个信号减去"同日全市场中位数收益" → 超额
        for k in FWD:
            b = res["date"].map(bench["fwd" + k])
            res["基准" + k] = b
            res["超额" + k] = res[k] - b
        o = io.open(r"d:\vibecoding\stock\ma15_backtest.txt", "w", encoding="utf-8")
        w = lambda s="": (print(s), o.write(s + "\n"))
        w(f"ma_atr15 回测 · 买入信号 {len(res)} 个 · {time.strftime('%Y-%m-%d %H:%M')}")
        w("基准 = 同一天全市场个股未来 N 日收益的中位数")
        w("=" * 66)
        for k in FWD:
            v = res[k].dropna()
            e = res["超额" + k].dropna()
            if not len(v):
                continue
            w(f"\n持有 {k} ({len(v)} 个样本)")
            w(f"  策略  平均 {v.mean():+.2f}%  中位 {v.median():+.2f}%  "
              f"胜率 {(v > 0).mean()*100:.1f}%")
            w(f"  基准  平均 {res['基准'+k].dropna().mean():+.2f}%")
            w(f"  >>> 超额 平均 {e.mean():+.2f}%  中位 {e.median():+.2f}%  "
              f"跑赢比例 {(e > 0).mean()*100:.1f}%")
            w(f"  最好 {v.max():+.1f}%  最差 {v.min():+.1f}%   标准差 {v.std():.1f}%")
            q = e.quantile([0.1, 0.25, 0.5, 0.75, 0.9])
            w("  超额分位: " + "  ".join(f"{int(a*100)}%={bb:+.1f}" for a, bb in q.items()))

        # ── 分组: 哪类信号的 5 日超额最高 ──
        key = "超额5日"
        w()
        w("=" * 66)
        w("分组检验 · 5日超额 (找哪类信号才有真 alpha)")
        w("=" * 66)
        groups = [
            ("信号时距慢线", "gap", [-99, -1, 0, 1, 3, 99]),
            ("慢>滤幅度%", "trend", [0, 2, 5, 10, 99]),
            ("ATR%", "atrp", [0, 1, 2, 4, 99]),
        ]
        for title, col, edges in groups:
            w(f"\n-- 按 {title} 分组 --")
            sub = res[[col, key]].dropna()
            if sub.empty:
                continue
            cut = pd.cut(sub[col], edges, right=False)
            for iv, gg in sub.groupby(cut, observed=True):
                if len(gg) < 50:
                    continue
                w(f"  {str(iv):<18} 样本{len(gg):>5}  5日超额均值 "
                  f"{gg[key].mean():+.2f}%  中位 {gg[key].median():+.2f}%  "
                  f"跑赢 {(gg[key] > 0).mean()*100:.0f}%")
        o.close()
        print("\n已保存 ma15_backtest.txt")


if __name__ == "__main__":
    main()

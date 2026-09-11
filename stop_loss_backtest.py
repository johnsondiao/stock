# -*- coding: utf-8 -*-
"""
止损规则敏感度回测

背景:
  连续多只票"刚卖就涨"(中国出版 6.01清→涨到6.95、铜陵有色、哈空调),
  怀疑现行的"收盘跌破 MA12 次日就走"太敏感, 容易被洗出去。
  但个例有幸存者偏差(中国出版后来又暴跌回 6.26), 必须回测。

对比三种卖出规则:
  A 现行 : 收盘跌破 MA12  -> 次日开盘卖
  B 确认 : 连续两天收盘在 MA12 下方 -> 次日开盘卖
  C 宽   : 收盘跌破 MA60  -> 次日开盘卖

统一入场: 收盘上穿 MA12 且 MA12 > MA60(趋势向上) -> 次日开盘买

同时统计"假摔率": 跌破 MA12 后, 次日就收复的比例。

用法: python stop_loss_backtest.py
"""
import io
import sqlite3
import numpy as np
import pandas as pd

DB = r"d:\vibecoding\stock\backend\data\stock.db"
OUT = r"d:\vibecoding\stock\stop_loss_backtest.txt"
START = "2025-01-01"
END = "2026-09-10"

BUY_FEE = 0.0003          # 买入佣金 万3
SELL_FEE = 0.0003 + 0.001  # 卖出佣金 + 印花税千一

_lines = []


def P(s=""):
    print(s)
    _lines.append(str(s))


def load():
    db = sqlite3.connect(DB, timeout=60)
    df = pd.read_sql_query(
        "SELECT code, substr(date,1,10) AS d, open, close FROM daily_kline "
        "WHERE date >= ? AND date <= ?", db, params=(START, END))
    db.close()
    px = df.pivot_table(index="d", columns="code", values="close",
                        aggfunc="last").sort_index()
    op = df.pivot_table(index="d", columns="code", values="open",
                        aggfunc="last").sort_index().reindex(
        index=px.index, columns=px.columns)
    return px, op


def run_exit(px, op, ma12, ma60, mode):
    """
    mode: 'A' 破MA12即走 / 'B' 连两天在MA12下才走 / 'C' 破MA60才走
    返回交易列表 [(code, buy_i, buy_price, sell_i, sell_price, days, ret)]
    """
    trades = []
    codes = px.columns
    for c in codes:
        s = px[c].values
        o = op[c].values
        m12 = ma12[c].values
        m60 = ma60[c].values
        n = len(s)
        pos = -1            # 持仓中的买入索引
        below = 0           # 连续收在 MA12 下方的天数
        for i in range(1, n):
            if np.isnan(s[i]) or np.isnan(m12[i]) or np.isnan(m60[i]):
                continue
            if pos < 0:
                # 入场: 昨日在MA12下(或持平), 今日上穿, 且 MA12 > MA60
                if (i > 0 and not np.isnan(s[i - 1]) and not np.isnan(m12[i - 1])
                        and s[i - 1] <= m12[i - 1] and s[i] > m12[i]
                        and m12[i] > m60[i]):
                    if i + 1 < n and np.isfinite(o[i + 1]) and o[i + 1] > 0:
                        pos = i + 1
                        buy_px = o[i + 1]
                        below = 0
            else:
                # 更新连续破位天数
                below = below + 1 if s[i] < m12[i] else 0
                sell = False
                if mode == "A" and s[i] < m12[i]:
                    sell = True
                elif mode == "B" and below >= 2:
                    sell = True
                elif mode == "C" and not np.isnan(m60[i]) and s[i] < m60[i]:
                    sell = True
                if (sell and i + 1 < n and np.isfinite(o[i + 1])
                        and o[i + 1] > 0):
                    sell_px = o[i + 1]
                    ret = (sell_px / buy_px - 1) * 100 - (BUY_FEE + SELL_FEE) * 100
                    trades.append((c, pos, i + 1, ret, i + 1 - pos))
                    pos = -1
                    below = 0
        # 末尾未平仓: 按该股最后一个有效收盘价平仓
        if 0 <= pos < n:
            valid = s[np.isfinite(s) & (s > 0)]
            if len(valid) and np.isfinite(buy_px) and buy_px > 0:
                ret = (valid[-1] / buy_px - 1) * 100 - (BUY_FEE + SELL_FEE) * 100
                trades.append((c, pos, n - 1, ret, n - 1 - pos))
    return trades


def pair_compare(px, op, ma12, ma60):
    """
    对每个入场点, 分别求 A(破MA12即走) 与 B(连两天在MA12下才走) 的卖出价,
    返回 (卖出价差%, 多等天数) 列表。
    价差 > 0 表示「多等一天卖」卖得更贵(即当天走是错的)。
    """
    diffs, waits = [], []
    for c in px.columns:
        s = px[c].values
        o = op[c].values
        m12 = ma12[c].values
        m60 = ma60[c].values
        n = len(s)
        valid = np.isfinite(s) & np.isfinite(m12) & np.isfinite(m60) & np.isfinite(o)
        below = valid & (s < m12)
        b2 = below.copy()
        b2[1:] = below[1:] & below[:-1]          # b2[j] = 连续两天在下方
        # 入场点: 昨日 <= MA12, 今日 > MA12, 且 MA12 > MA60
        ent = np.zeros(n, dtype=bool)
        ent[1:] = (valid[1:] & valid[:-1] & (s[1:] > m12[1:])
                   & (s[:-1] <= m12[:-1]) & (m12[1:] > m60[1:]))
        for i in np.flatnonzero(ent):
            bi = i + 1                            # 次日开盘买入
            if bi >= n - 1:
                continue
            sa = below[bi:]
            sb = b2[bi:]
            if not sa.any() or not sb.any():
                continue
            ja = bi + int(sa.argmax())
            jb = bi + int(sb.argmax())
            if ja + 1 >= n or jb + 1 >= n:
                continue
            pa, pb = o[ja + 1], o[jb + 1]
            if not (pa > 0 and pb > 0 and np.isfinite(pa) and np.isfinite(pb)):
                continue
            diffs.append((pb / pa - 1) * 100)
            waits.append(jb - ja)
    return diffs, waits


def summarize(trades, px, label):
    if not trades:
        P(f"{label}: 无交易")
        return
    r = np.array([t[3] for t in trades], dtype=float)
    d = np.array([t[4] for t in trades], dtype=float)
    ok = np.isfinite(r)
    r, d = r[ok], d[ok]
    if len(r) == 0:
        P(f"{label}: 无有效交易")
        return
    win = (r > 0).mean() * 100
    gain = r[r > 0].mean() if (r > 0).any() else 0.0
    loss = r[r < 0].mean() if (r < 0).any() else 0.0
    pl = gain / abs(loss) if loss else float("nan")
    # 注: 不做"累计收益/最大回撤" —— 交易横跨不同日期且大量重叠,
    # 单笔复利连乘出来的数字没有意义, 会严重误导。
    P(f"{label:<22} 交易{len(r):>5}笔  胜率{win:>5.1f}%  "
      f"平均{r.mean():>+6.2f}%  中位{np.median(r):>+6.2f}%  "
      f"盈亏比{pl:>5.2f}  持有{d.mean():>5.1f}天  "
      f"亏超5%占{(r < -5).mean()*100:>3.0f}%")
    return r


def main():
    P("止损规则敏感度回测")
    P("=" * 96)
    P(f"生成时间: {pd.Timestamp.now():%Y-%m-%d %H:%M}")
    P("")
    P("问题: 现行的「收盘跌破 MA12 第二天就卖」是不是太急了? 容不容易被洗出去?")
    P("做法: 用同一套买入信号, 只换卖出规则, 全市场回测看长期哪个赚得多")
    P("")

    px, op = load()
    P(f"数据: {len(px)} 个交易日 × {px.shape[1]} 只股票 "
      f"({px.index[0]} ~ {px.index[-1]})")
    ma12 = px.rolling(12, min_periods=10).mean()
    ma60 = px.rolling(60, min_periods=40).mean()

    # ---- 假摔率: 跌破 MA12 后次日收复的比例 ----
    P("")
    P("=" * 96)
    P("检验一: 跌破 MA12 之后, 有多少是「假摔」?")
    P("=" * 96)
    brk = (px.shift(1) >= ma12.shift(1)) & (px < ma12)
    rec = brk.shift(1).fillna(False) & (px >= ma12)
    tot = int(brk.values.sum())
    tot_rec = int(rec.values.sum())
    P(f"  跌破 MA12 的次数: {tot}")
    P(f"  次日就收复(假摔): {tot_rec}  ({tot_rec / max(tot,1) * 100:.1f}%)")
    P(f"  次日继续在下方  : {tot - tot_rec}  ({(tot-tot_rec)/max(tot,1)*100:.1f}%)")
    P("")
    P("  → 假摔率越高, 说明「当天就走」越容易误杀")

    # 假摔之后 vs 真破位之后, 未来表现
    fwd = {}
    for k in (5, 10, 20):
        fwd[k] = (px.shift(-k) / px - 1) * 100
    P("")
    P(f"{'情形':<20}{'样本':>7}{'未来5日':>10}{'未来10日':>10}{'未来20日':>10}")
    P("-" * 96)
    for lab, m in [("次日收复(假摔)", rec), ("次日仍在下方(真破)", brk.shift(1).fillna(False) & (px < ma12))]:
        vals = [fwd[k].values[m.values] for k in (5, 10, 20)]
        vv = [v[~np.isnan(v)] for v in vals]
        cnt = len(vv[0])
        P(f"{lab:<20}{cnt:>7}" + "".join(f"{v.mean():>+10.2f}" for v in vv))

    # ---- 三种规则回测 ----
    P("")
    P("=" * 96)
    P("检验二: 三条卖出规则全市场回测 (买入信号完全相同)")
    P("=" * 96)
    P("  入场: 收盘站上 MA12 且 MA12 > MA60 -> 次日开盘买")
    P("  费用: 买入万3 + 卖出万3+印花税千一, 已计入")
    P("")
    res = {}
    for mode, lab in [("A", "A 破MA12即走(现行)"),
                      ("B", "B 连跌两天确认才走"),
                      ("C", "C 破MA60才走(很宽)")]:
        tr = run_exit(px, op, ma12, ma60, mode)
        res[lab] = tr
        summarize(tr, px, lab)

    P("")
    P("=" * 96)
    P("检验三: 同一批买入点, 「当天就走」 vs 「多等一天」卖出价差 (配对比较)")
    P("=" * 96)
    P("  做法: 找到每个入场点, 算出 A 会卖在哪天、B 会卖在哪天, 直接比卖出价")
    P("  这正是你纠结的那一次: 破位当天跑了, 多等一天是赚还是亏?")
    P("")
    diffs, waits = pair_compare(px, op, ma12, ma60)
    if len(diffs):
        d = np.array(diffs)
        w = np.array(waits)
        P(f"  可比样本: {len(d)} 次")
        P(f"  多等一天后卖出价 平均 {(d).mean():+.2f}%  "
          f"中位 {np.median(d):+.2f}%")
        P(f"  多等一天更划算的占 {(d > 0).mean()*100:.1f}%  "
          f"(更差的占 {(d < 0).mean()*100:.1f}%, 持平 {(d == 0).mean()*100:.1f}%)")
        P(f"  平均多等了 {w.mean():.1f} 个交易日")
        P("")
        P("  分档看(多等一天的收益分布):")
        for q in (10, 25, 50, 75, 90):
            P(f"    {q:>2}% 分位: {np.percentile(d, q):+.2f}%")
        big = (d > 2).mean() * 100
        bad = (d < -2).mean() * 100
        P(f"  多等一天多赚超2%: {big:.1f}%   多亏超2%: {bad:.1f}%")

    P("")
    P("=" * 96)
    P("检验四: A 与 B 的整体差异")
    P("=" * 96)
    ra = np.array([t[3] for t in res["A 破MA12即走(现行)"]], dtype=float)
    rb = np.array([t[3] for t in res["B 连跌两天确认才走"]], dtype=float)
    ra = ra[np.isfinite(ra)]
    rb = rb[np.isfinite(rb)]
    P(f"  A: {len(ra)} 笔, 平均 {ra.mean():+.2f}%, 亏损超5%占 {(ra<-5).mean()*100:.0f}%")
    P(f"  B: {len(rb)} 笔, 平均 {rb.mean():+.2f}%, 亏损超5%占 {(rb<-5).mean()*100:.0f}%")
    P(f"  单笔差 (B-A): {rb.mean() - ra.mean():+.2f} 个百分点/笔")
    P(f"  交易次数 B 比 A 少 {len(ra) - len(rb)} 笔 "
      f"({(1 - len(rb)/max(len(ra),1))*100:.0f}%) —— 少动=少交费")

    P("")
    P("=" * 96)
    P("结论")
    P("=" * 96)
    best = max(res.items(), key=lambda kv: np.mean([t[3] for t in kv[1]]) if kv[1] else -99)
    P(f"1. 假摔率 {tot_rec/max(tot,1)*100:.0f}% —— 破位后次日就收复的比例")
    P(f"2. 单笔平均收益最高的是: {best[0]} "
      f"({np.mean([t[3] for t in best[1]]):+.2f}%)")
    P("3. 注意: 以上是全市场等额下注的统计, 未按你的资金规模加权")
    P("4. 以上为 2025 年以来的历史统计, 不构成投资建议")

    io.open(OUT, "w", encoding="utf-8").write("\n".join(_lines))


if __name__ == "__main__":
    main()

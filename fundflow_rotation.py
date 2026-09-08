# -*- coding: utf-8 -*-
"""
资金流 → 板块轮动 实证分析

回答一个问题: 钱往哪个板块流, 那个板块接下来真的会涨吗?

数据源: fund_flow 表(新浪主力资金流, netamount=超大单+大单净额, ratio=净流入占成交额比)
行业口径: industry_map.csv (49 行业)
未来收益: 用 fund_flow.close 计算个股收益后取行业中位数(不依赖 daily_kline)

检验内容:
  检验一 分档单调性: 按因子把行业分5档, 看未来收益是否从低到高递增
  检验二 前8名表现: 资金流入最多的8个行业, 未来5/10日 vs 全行业
  检验三 不同因子对比: 单日 / 5日累计 / 趋势强度 / 连续流入天数
  检验四 样本外: 前半段选出的最优因子, 拿到后半段验证
  检验五 今日快照: 各因子当前排名
"""
import io
import sqlite3
import numpy as np
import pandas as pd

DB = r"d:\vibecoding\stock\backend\data\stock.db"
IND = r"d:\vibecoding\stock\industry_map.csv"
OUT = r"d:\vibecoding\stock\fundflow_rotation.txt"
START = "2025-01-01"          # 全市场日线覆盖起点
W = 5                          # 因子回看窗口(交易日)
FWD = {"5日": 5, "10日": 10, "20日": 20}
TOPN = 8

_lines = []


def P(s=""):
    print(s)
    _lines.append(str(s))


def load():
    db = sqlite3.connect(DB, timeout=60)
    df = pd.read_sql_query(
        "SELECT code, date, netamount, ratio, close FROM fund_flow "
        "WHERE date >= ?", db, params=(START,))
    db.close()
    ind = pd.read_csv(IND, encoding="utf-8-sig", dtype=str)
    imap = dict(zip(ind["code"], ind["sector"]))
    df["sec"] = df["code"].map(imap)
    df = df.dropna(subset=["sec"])
    return df, imap


def build(df):
    """构造行业 x 日期 面板"""
    net = df.pivot_table(index="date", columns="sec", values="netamount",
                         aggfunc="sum")
    rat = df.pivot_table(index="date", columns="sec", values="ratio",
                         aggfunc="median")
    cnt = df.pivot_table(index="date", columns="sec", values="code",
                         aggfunc="count")
    # 个股收盘价矩阵 -> 行业未来收益
    px = df.pivot_table(index="date", columns="code", values="close",
                        aggfunc="last")
    return net, rat, cnt, px


def sec_future(px, imap, n):
    """行业未来 n 日收益(个股中位数)"""
    fut = px.shift(-n) / px - 1
    cols = {}
    for code, sec in imap.items():
        cols.setdefault(sec, []).append(code)
    out = {}
    for sec, codes in cols.items():
        cs = [c for c in codes if c in fut.columns]
        if len(cs) >= 3:
            out[sec] = fut[cs].median(axis=1) * 100
    return pd.DataFrame(out)


def factors(net, rat, cnt, w):
    """返回 dict: 因子名 -> 行业 x 日期 因子值矩阵"""
    f = {}
    # F1 近w日累计净流入(按行业股票数摊平, 单位: 万元/只)
    f["F1累计净流入"] = net.rolling(w).sum() / cnt.rolling(w).mean() / 1e4
    # F2 近w日净流入占比中位数(ratio 均值, 已天然标准化)
    f["F2净流入占比"] = rat.rolling(w).mean()
    # F3 趋势强度(中银口径): mean(日净流入)/mean(|日净流入|) ∈ [-1,1]
    f["F3趋势强度"] = net.rolling(w).mean() / net.abs().rolling(w).mean()
    # F4 近w日净流入天数占比
    f["F4流入天数"] = (net > 0).rolling(w).mean()
    # F5 近w日连续流入天数(截至当日)
    pos = (net > 0).astype(float)
    streak = pos.copy()
    for i in range(1, w):
        streak = streak * 1.0
    # 用累计方式近似: 近w日全为正则=w
    f["F5连续流入"] = (net > 0).rolling(w).apply(lambda x: float(x.all()) * w
                                                 if x.all() else
                                                 (float((x[::-1].cumprod().sum()))),
                                                 raw=True)
    # F0 单日(对照)
    f["F0单日净流入"] = net / cnt / 1e4
    return f


def _broadcast_mkt(fuk):
    """把每期全行业平均收益广播成 行业x日期 矩阵, 便于逐元素对齐"""
    mkt = fuk.mean(axis=1)
    return pd.DataFrame(
        np.repeat(mkt.values[:, None], fuk.shape[1], axis=1),
        index=fuk.index, columns=fuk.columns)


def _pick(val_df, mkt_df, mask):
    """按 mask 取出 (收益, 同行平均) 两个完全对齐的一维 Series"""
    v = val_df[mask].stack()
    m = mkt_df[mask].stack()
    ok = v.notna() & m.notna()
    return v[ok], m[ok]


def eval_factor(fmat, fu, name, w):
    """评估单个因子: 分档单调性 + 前N名表现。fu 为 {周期: 行业x日期收益矩阵}"""
    P(f"\n--- {name} (回看{w}日) ---")
    res = {}
    idx = fmat.index
    for k in FWD:
        idx = idx.intersection(fu[k].index)
    fm = fmat.reindex(idx)
    valid = fm.notna().sum(axis=1)
    idx = idx[valid >= 20]                      # 该期至少20个行业有值
    fm = fm.reindex(idx)

    for k in FWD:
        fuk = fu[k].reindex(idx)
        mkt_df = _broadcast_mkt(fuk)
        ranks = fm.rank(axis=1, ascending=False)
        buckets = {}
        for lo, hi, lab in [(1, 10, "Q1(流入最多)"), (11, 19, "Q2"),
                            (20, 29, "Q3"), (30, 38, "Q4"),
                            (39, 49, "Q5(流出最多)")]:
            v, m = _pick(fuk, mkt_df, (ranks >= lo) & (ranks <= hi))
            if len(v) > 30:
                buckets[lab] = (v, m)
        vt, mt = _pick(fuk, mkt_df, ranks <= TOPN)
        if len(vt) < 30:
            continue
        ex = vt - mt
        P(f"  [{k}] 前{TOPN}名: 收益{vt.mean():+.2f}%  "
          f"超额{ex.mean():+.2f}%  跑赢{(ex>0).mean()*100:.0f}%  样本{len(vt)}")
        if k == "5日":
            P("      分档 (相对全行业超额):")
            for lab, (v, m) in buckets.items():
                e = v - m
                P(f"        {lab:<12} 收益{v.mean():+.2f}%  超额{e.mean():+.2f}%  "
                  f"跑赢{(e>0).mean()*100:.0f}%  n={len(v)}")
        res[k] = {"ex": ex.mean(), "win": (ex > 0).mean() * 100, "n": len(vt),
                  "raw": vt.mean()}
    return res


def main():
    df, imap = load()
    P(f"资金流记录 {len(df)} 行 / {df['code'].nunique()} 只 / "
      f"{df['date'].min()} ~ {df['date'].max()} / {df['sec'].nunique()} 个行业")
    net, rat, cnt, px = build(df)
    P(f"行业面板: {net.shape[0]} 个交易日 x {net.shape[1]} 个行业")

    futs = {}
    for k, n in FWD.items():
        futs[k] = sec_future(px, imap, n)
    fut = pd.concat({k: v for k, v in futs.items()}, axis=1)
    fut.columns = [f"{a}|{b}" for a, b in fut.columns]
    # 拆成 dict of DataFrame
    fu = {k: fut[[c for c in fut.columns if c.startswith(k + "|")]]
          .rename(columns=lambda x: x.split("|")[1]) for k in FWD}
    for k in fu:
        fu[k] = fu[k].reindex(net.index)

    P("\n" + "=" * 72)
    P("检验一/二/三: 各因子表现 (未来收益 = 行业个股中位数)")
    P("=" * 72)

    fdict = factors(net, rat, cnt, W)
    summary = {}
    for name, fmat in fdict.items():
        w = 1 if name.startswith("F0") else W
        summary[name] = eval_factor(fmat, fu, name, w)

    # ---- 样本外 ----
    P("\n" + "=" * 72)
    P("检验四: 样本外验证 (前半段选因子, 后半段验证)")
    P("=" * 72)
    n = len(net)
    half = n // 2
    P(f"训练段 {net.index[0]} ~ {net.index[half-1]} ({half}日)  |  "
      f"测试段 {net.index[half]} ~ {net.index[-1]} ({n-half}日)")

    def top_excess(fmat, fuk, topn=TOPN):
        """给定因子矩阵与收益矩阵, 返回前topn名的 (超额, 跑赢率, 样本数)"""
        idx = fmat.index.intersection(fuk.index)
        fm = fmat.reindex(idx)
        f5 = fuk.reindex(idx)
        fm = fm[fm.notna().sum(axis=1) >= 20]
        f5 = f5.reindex(fm.index)
        rk = fm.rank(axis=1, ascending=False)
        v, m = _pick(f5, _broadcast_mkt(f5), rk <= topn)
        if len(v) < 30:
            return None
        e = v - m
        return e.mean(), (e > 0).mean() * 100, len(v)

    best = None
    P("\n【训练段】各因子未来5日超额:")
    for name, fmat in fdict.items():
        r = top_excess(fmat.iloc[:half], fu["5日"])
        if r is None:
            continue
        ex, win, n = r
        P(f"  {name:<12} 超额{ex:+.2f}%  跑赢{win:.0f}%  n={n}")
        if best is None or ex > best[1]:
            best = (name, ex, win)
    if best:
        P(f"\n训练段最优因子: {best[0]} (超额{best[1]:+.2f}%)")
        P("\n【测试段】同一因子在未见数据上的表现:")
        r = top_excess(fdict[best[0]].iloc[half:], fu["5日"])
        if r:
            ex_t, win_t, n_t = r
            P(f"  {best[0]:<12} 超额{ex_t:+.2f}%  跑赢{win_t:.0f}%  n={n_t}")
            if abs(best[1]) > 1e-9:
                P(f"  → 保留率 {ex_t/best[1]*100:.0f}%")
            else:
                P("  → 训练段超额接近0, 保留率无意义")
        P("\n  [对照] 测试段全部因子:")
        for name, fmat in fdict.items():
            r = top_excess(fmat.iloc[half:], fu["5日"])
            if r:
                P(f"    {name:<12} 超额{r[0]:+.2f}%  跑赢{r[1]:.0f}%  n={r[2]}")

    # ---- 检验六: 资金流是否只是过去涨幅的影子 ----
    P("\n" + "=" * 72)
    P("检验六: 资金流 vs 过去涨幅 (资金流到底有没有独立信息?)")
    P("=" * 72)

    ret_d = px.pct_change()
    cols = {}
    for code, sec in imap.items():
        cols.setdefault(sec, []).append(code)
    sec_ret = {}
    for sec, cs in cols.items():
        cs = [c for c in cs if c in ret_d.columns]
        if len(cs) >= 3:
            sec_ret[sec] = ret_d[cs].median(axis=1)
    sec_ret = pd.DataFrame(sec_ret).reindex(net.index) * 100
    past = sec_ret.rolling(W).sum()             # 过去W日涨幅

    f1 = fdict["F1累计净流入"]
    idx = f1.index.intersection(past.index).intersection(fu["5日"].index)
    f1a, pa, f5a = f1.reindex(idx), past.reindex(idx), fu["5日"].reindex(idx)
    ok = f1a.notna().sum(axis=1) >= 20
    f1a, pa, f5a = f1a[ok], pa[ok], f5a[ok]

    # (1) 横截面相关性
    cors = []
    for d in f1a.index:
        x, y = f1a.loc[d], pa.loc[d]
        m = x.notna() & y.notna()
        if m.sum() >= 20 and x[m].std() > 0 and y[m].std() > 0:
            cors.append(np.corrcoef(x[m], y[m])[0, 1])
    P(f"\n(1) 资金流 与 过去{W}日涨幅 的横截面相关系数: 平均 {np.mean(cors):+.3f} "
      f"(共{len(cors)}期, 标准差 {np.std(cors):.3f})")
    P("    → 接近1说明资金流基本就是'过去涨得多'的另一种说法, 没有独立信息")

    # (2) 二维分组: 过去涨幅 x 资金流
    P(f"\n(2) 二维分组 (行=过去{W}日涨幅, 列=资金流, 数值=未来5日超额)")
    rk_f = f1a.rank(axis=1, pct=True)
    rk_p = pa.rank(axis=1, pct=True)
    labs_p = [("涨得多(前1/3)", rk_p > 2/3), ("中间", (rk_p >= 1/3) & (rk_p <= 2/3)),
              ("跌得多(后1/3)", rk_p < 1/3)]
    labs_f = [("流入多", rk_f > 2/3), ("中间", (rk_f >= 1/3) & (rk_f <= 2/3)),
              ("流出多", rk_f < 1/3)]
    mkt_df = _broadcast_mkt(f5a)
    P(f"    {'':<16}{'流入多':>22}{'中间':>22}{'流出多':>22}")
    for plab, pmask in labs_p:
        row = f"{'':<6}{plab:<10}"
        for flab, fmask in labs_f:
            v, m = _pick(f5a, mkt_df, pmask & fmask)
            if len(v) > 30:
                row += f"{(v-m).mean():>+14.2f}%(跑赢{(v-m>0).mean()*100:>3.0f}%)"
            else:
                row += f"{'样本不足':>22}"
        P(row)

    # (3) 量价背离
    P("\n(3) 量价背离信号 (最能检验资金流的独立价值)")
    divs = {
        "跌了但资金流入 (抄底)": (rk_p < 1/3) & (rk_f > 2/3),
        "涨了但资金流出 (派发)": (rk_p > 2/3) & (rk_f < 1/3),
        "涨了资金也进 (共振)":   (rk_p > 2/3) & (rk_f > 2/3),
        "跌了资金也走 (踩踏)":   (rk_p < 1/3) & (rk_f < 1/3),
    }
    for lab, m in divs.items():
        v, mm = _pick(f5a, mkt_df, m)
        if len(v) > 30:
            e = v - mm
            P(f"    {lab:<22} 未来5日 {v.mean():+.2f}%  超额{e.mean():+.2f}%  "
              f"跑赢{(e>0).mean()*100:.0f}%  n={len(v)}")

    # (4) 唯一正超额信号必须过样本外这一关
    P("\n(4) '涨了但资金流出' 信号 样本外验证 (防多重检验假象)")
    sig = (rk_p > 2/3) & (rk_f < 1/3)
    for lab, sl in [("训练段", slice(0, half)), ("测试段", slice(half, None))]:
        s_f5 = f5a.iloc[sl]; s_m = mkt_df.iloc[sl]; s_sig = sig.iloc[sl]
        v, mm = _pick(s_f5, s_m, s_sig)
        if len(v) > 30:
            e = v - mm
            P(f"    {lab}: 未来5日 {v.mean():+.2f}%  超额{e.mean():+.2f}%  "
              f"跑赢{(e>0).mean()*100:.0f}%  n={len(v)}")

    # ---- 今日快照 ----
    P("\n" + "=" * 72)
    P("检验七: 今日资金流快照")
    P("=" * 72)
    for name in ["F1累计净流入", "F2净流入占比", "F3趋势强度", "F4流入天数"]:
        fmat = fdict[name]
        last = fmat.iloc[-1].dropna().sort_values(ascending=False)
        P(f"\n【{name}】截至 {fmat.index[-1]}")
        P(f"  {'行业':<10}{'因子值':>12}   |  {'行业':<10}{'因子值':>12}")
        top, bot = last.head(8), last.tail(5)
        for i in range(8):
            a = f"  {top.index[i]:<10}{top.iloc[i]:>12.3f}"
            b = ""
            if i < len(bot):
                b = f"  |  {bot.index[-(i+1)]:<10}{bot.iloc[-(i+1)]:>12.3f}"
            P(a + b)

    io.open(OUT, "w", encoding="utf-8").write("\n".join(_lines))
    print(f"\n已保存 {OUT}")


if __name__ == "__main__":
    main()

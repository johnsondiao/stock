# -*- coding: utf-8 -*-
"""
板块启动识别: 板块刚涨起来的时候, 怎么判断它是真启动还是假反弹?

思路:
  不预测"下一个是谁", 而是等板块已经启动时, 用启动时的特征判断真假。

启动定义:
  某板块 5 日涨幅首次进入全市场前 10 名(上一期不在前 10)
  每个板块每波行情只算一次, 避免重复计数

区分特征(启动时观察):
  up5    板块内近 5 日上涨股票占比      —— 广度: 大家一起涨才是真启动
  lead   5日涨幅均值 - 中位数           —— 龙头拉动: 越大说明越靠少数股硬拉
  pos60  板块在近 60 日区间的位置 0~1   —— 位置: 高位启动风险大
  amp    板块 5 日涨幅本身               —— 幅度: 涨太猛容易透支
  cons   近 5 日板块内上涨占比的稳定性

检验:
  检验一 全部启动事件: 未来10/20日 vs 全行业平均
  检验二 单特征分组: 广度 / 龙头拉动 / 位置 / 幅度
  检验三 组合条件: 温和启动 + 广度好 + 位置不高
  检验四 样本外验证
  检验五 当前正在启动的板块
"""
import io
import sqlite3
import numpy as np
import pandas as pd

DB = r"d:\vibecoding\stock\backend\data\stock.db"
IND = r"d:\vibecoding\stock\industry_map.csv"
OUT = r"d:\vibecoding\stock\sector_breakout.txt"
START = "2025-01-01"
TOPN = 10          # 前 N 名算强势
W = 5              # 启动回看窗口

_lines = []


def P(s=""):
    print(s)
    _lines.append(str(s))


def load():
    db = sqlite3.connect(DB, timeout=60)
    df = pd.read_sql_query(
        "SELECT code, substr(date,1,10) AS d, close FROM daily_kline "
        "WHERE date >= ?", db, params=(START,))
    db.close()
    ind = pd.read_csv(IND, encoding="utf-8-sig", dtype=str)
    imap = dict(zip(ind["code"], ind["sector"]))
    return df, imap


def build(df, imap):
    px = df.pivot_table(index="d", columns="code", values="close",
                        aggfunc="last").sort_index()
    r1 = px.pct_change()
    r5 = px / px.shift(W) - 1

    cols = {}
    for c, s in imap.items():
        cols.setdefault(s, []).append(c)

    med, up, lead, amp, up1 = {}, {}, {}, {}, {}
    for s, cs in cols.items():
        cs = [c for c in cs if c in px.columns]
        if len(cs) < 5:
            continue
        x5 = r5[cs]
        x1 = r1[cs]
        med[s] = x5.median(axis=1) * 100                    # 板块5日涨幅(中位)
        up[s] = (x5 > 0).mean(axis=1) * 100                 # 5日上涨占比
        lead[s] = (x5.mean(axis=1) - x5.median(axis=1)) * 100
        amp[s] = x5.max(axis=1) * 100                       # 板块内最强股涨幅
        up1[s] = (x1 > 0).mean(axis=1) * 100

    # 板块指数: 用"个股日收益中位数"累乘, 不能用中位价格(会随成分股切换跳变)
    sec_ret = {}
    for s, cs in cols.items():
        cs = [c for c in cs if c in px.columns]
        if len(cs) >= 5:
            sec_ret[s] = r1[cs].median(axis=1)
    sec_ret = pd.DataFrame(sec_ret).reindex(px.index).fillna(0.0)
    pxsec = (1.0 + sec_ret).cumprod()

    M = pd.DataFrame(med).reindex(px.index)
    U = pd.DataFrame(up).reindex(px.index)
    L = pd.DataFrame(lead).reindex(px.index)
    A = pd.DataFrame(amp).reindex(px.index)
    U1 = pd.DataFrame(up1).reindex(px.index)

    lo = pxsec.rolling(60, min_periods=30).min()
    hi = pxsec.rolling(60, min_periods=30).max()
    POS = ((pxsec - lo) / (hi - lo).replace(0, np.nan) * 100).reindex(px.index)

    FUT = {}
    for n in (10, 20):
        FUT[n] = (pxsec.shift(-n) / pxsec - 1) * 100
    return M, U, L, A, U1, POS, FUT, pxsec


def stats(val_df, mask, fut_df, label, minn=40):
    """给定事件 mask, 输出未来10/20日表现"""
    out = {}
    for n in (10, 20):
        v = fut_df[n][mask].stack().dropna()
        if len(v) < minn:
            out[n] = None
            continue
        mkt = fut_df[n].mean(axis=1)
        # 广播同行平均
        mk = pd.DataFrame(np.repeat(mkt.values[:, None], fut_df[n].shape[1],
                                    axis=1), index=fut_df[n].index,
                          columns=fut_df[n].columns)[mask].stack().dropna()
        common = v.index.intersection(mk.index)
        v, mk = v[common], mk[common]
        e = v - mk
        out[n] = (v.mean(), e.mean(), (e > 0).mean() * 100, len(v))
    if out.get(10):
        r = out[10]
        P(f"  {label:<26} 未来10日 {r[0]:+.2f}%  超额{r[1]:+.2f}%  "
          f"跑赢{r[2]:>3.0f}%  n={r[3]}")
    if out.get(20):
        r = out[20]
        P(f"  {'':<26} 未来20日 {r[0]:+.2f}%  超额{r[1]:+.2f}%  "
          f"跑赢{r[2]:>3.0f}%  n={r[3]}")
    return out


def main():
    df, imap = load()
    M, U, L, A, U1, POS, FUT, pxsec = build(df, imap)
    P(f"样本: {M.shape[0]} 个交易日 x {M.shape[1]} 个行业  "
      f"({M.index[0]} ~ {M.index[-1]})")

    rank = M.rank(axis=1, ascending=False)
    in_top = rank <= TOPN
    # 启动事件: 冲进前N, 且过去5天最好排名也在20名开外
    # (排除在排名边缘反复进出的抖动, 确保是"新面孔")
    prev_best = rank.rolling(5, min_periods=1).min().shift(1)
    event = in_top & (prev_best > 20)
    P(f"\n启动事件总数: {int(event.values.sum())}  "
      f"(平均每个板块 {event.values.sum()/M.shape[1]:.1f} 次)")

    P("\n" + "=" * 74)
    P("检验一: 板块刚进前10时买入, 表现如何? (全部事件)")
    P("=" * 74)
    base = stats(M, event, FUT, "全部启动事件")

    P("\n" + "=" * 74)
    P("检验二: 按启动时的特征分组")
    P("=" * 74)

    P("\n[广度] 启动前5日, 板块内有多少比例的股票在涨")
    for lo, hi, lab in [(0, 40, "<40% (少数股拉)"), (40, 60, "40~60%"),
                        (60, 80, "60~80%"), (80, 101, ">80% (全面上涨)")]:
        stats(M, event & (U >= lo) & (U < hi), FUT, lab)

    P("\n[龙头拉动] 5日涨幅均值-中位数, 越大说明越靠少数暴涨股")
    qs = L[event].stack().quantile([1/3, 2/3])
    for lo, hi, lab in [(-99, qs[1/3], "小(齐涨)"),
                        (qs[1/3], qs[2/3], "中"),
                        (qs[2/3], 99, "大(龙头独拉)")]:
        stats(M, event & (L >= lo) & (L < hi), FUT, lab)

    P("\n[位置] 启动点在近60日区间的什么高度 (0=底部 100=顶部)")
    for lo, hi, lab in [(0, 30, "底部区 0~30"), (30, 60, "中部 30~60"),
                        (60, 85, "偏高位 60~85"), (85, 101, "顶部区 85~100")]:
        stats(M, event & (POS >= lo) & (POS < hi), FUT, lab)

    P("\n[幅度] 板块5日涨幅本身")
    for lo, hi, lab in [(-99, 3, "温和 <3%"), (3, 6, "中等 3~6%"),
                        (6, 99, "猛烈 >6%")]:
        stats(M, event & (M >= lo) & (M < hi), FUT, lab)

    P("\n" + "=" * 74)
    P("检验三: 组合条件 (真启动应该长什么样)")
    P("=" * 74)
    combos = {
        "温和(<6%) + 广度>60%":            event & (M < 6) & (U > 60),
        "温和(<6%) + 广度>60% + 非顶部":    event & (M < 6) & (U > 60) & (POS < 85),
        "温和 + 广度>60% + 齐涨(lead低)":   event & (M < 6) & (U > 60) &
                                            (L < L[event].stack().quantile(1/3)),
        "底部启动 + 广度>60%":              event & (POS < 40) & (U > 60),
        "猛烈(>6%) 或 顶部启动":            event & ((M > 6) | (POS > 85)),
    }
    for lab, m in combos.items():
        stats(M, m, FUT, lab)

    P("\n" + "=" * 74)
    P("检验四: 样本外验证 (前半段挑最优条件, 后半段验证)")
    P("=" * 74)
    n = len(M)
    half = n // 2
    P(f"训练段 {M.index[0]} ~ {M.index[half-1]}  |  "
      f"测试段 {M.index[half]} ~ {M.index[-1]}")

    def seg_excess(mask, sl, n_fut=10):
        f = FUT[n_fut].iloc[sl]
        mk = pd.DataFrame(np.repeat(f.mean(axis=1).values[:, None], f.shape[1],
                                    axis=1), index=f.index, columns=f.columns)
        m = mask.iloc[sl]
        v = f[m].stack().dropna()
        k = mk[m].stack().dropna()
        c = v.index.intersection(k.index)
        if len(c) < 30:
            return None
        e = v[c] - k[c]
        return e.mean(), (e > 0).mean() * 100, len(c)

    best, bestv = None, -99
    for lab, m in combos.items():
        r = seg_excess(m, slice(0, half))
        if r and r[0] > bestv:
            best, bestv = lab, r[0]
        if r:
            P(f"  训练 {lab:<30} 超额{r[0]:+.2f}%  跑赢{r[1]:.0f}%  n={r[2]}")
    P("")
    for lab, m in combos.items():
        r = seg_excess(m, slice(half, None))
        if r:
            mark = "  <<<" if lab == best else ""
            P(f"  测试 {lab:<30} 超额{r[0]:+.2f}%  跑赢{r[1]:.0f}%  n={r[2]}{mark}")
    if best:
        r = seg_excess(combos[best], slice(half, None))
        if r and abs(bestv) > 1e-9:
            P(f"\n  训练段最优: {best} (超额{bestv:+.2f}%)")
            P(f"  测试段表现: 超额{r[0]:+.2f}%  跑赢{r[1]:.0f}%  "
              f"→ 保留率 {r[0]/bestv*100:.0f}%")

    P("\n" + "=" * 74)
    P("检验五: 当前正在启动的板块")
    P("=" * 74)
    # 注意: 最新交易日可能只有少数股票入库, 必须挑最后一个"完整"交易日
    cnt = M.notna().sum(axis=1)
    good = cnt[cnt >= 30]
    if len(good) and good.index[-1] != M.index[-1]:
        P(f"(跳过不完整的 {M.index[-1]}, 该日仅 {int(cnt.iloc[-1])} 个行业有数据)")
    recent = event.iloc[-15:]
    hits = [(d, s) for d in recent.index for s in M.columns if recent.loc[d, s]]
    if hits:
        P(f"\n近 15 个交易日内出现启动信号的板块 ({M.index[-1]} 为最新):")
        P(f"  {'日期':<12}{'行业':<10}{'5日涨幅':>9}{'上涨占比':>9}"
          f"{'龙头拉动':>9}{'60日位置':>9}  评价")
        for d, s in hits[-14:]:
            ev = []
            if M.loc[d, s] < 6:
                ev.append("温和")
            elif M.loc[d, s] > 10:
                ev.append("过猛")
            if U.loc[d, s] > 60:
                ev.append("广度好")
            elif U.loc[d, s] < 40:
                ev.append("少数股拉")
            if POS.loc[d, s] < 40:
                ev.append("低位")
            elif POS.loc[d, s] > 85:
                ev.append("高位")
            P(f"  {d:<12}{s:<10}{M.loc[d,s]:>9.2f}{U.loc[d,s]:>9.0f}"
              f"{L.loc[d,s]:>9.2f}{POS.loc[d,s]:>9.0f}  {'/'.join(ev)}")
    else:
        P("\n近 15 个交易日无新启动板块")

    io.open(OUT, "w", encoding="utf-8").write("\n".join(_lines))
    print(f"\n已保存 {OUT}")


if __name__ == "__main__":
    main()

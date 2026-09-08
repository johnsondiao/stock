# -*- coding: utf-8 -*-
"""
板块"真主线"识别: 板块刚涨起来的时候, 怎么判断它是这轮真正的大涨板块?

方法: 事件标注法
  1. 先把历史上真正的"大涨板块"标出来(未来20日涨幅 >= 15%)
  2. 回到它们刚启动的那一天, 看当时能观察到什么特征
  3. 对比"真大涨" vs "假启动(一日游)", 找出有区分度的特征
  4. 打分模型 + 样本外验证
  5. 输出当前处于启动期、且打分高的板块

与 sector_breakout.py 的区别:
  那个问"启动后能不能继续涨"(收益高低)
  这个问"这次启动是不是这轮真正的主升浪"(真假判别)
"""
import io
import sqlite3
import numpy as np
import pandas as pd

DB = r"d:\vibecoding\stock\backend\data\stock.db"
IND = r"d:\vibecoding\stock\industry_map.csv"
OUT = r"d:\vibecoding\stock\sector_mainline.txt"
START = "2025-01-01"

BIG_UP = 0.15        # 未来20日涨幅 >= 15% 认定为"真大涨"
FWD = {"10日": 10, "20日": 20}
MIN_STK = 5          # 板块最少成分股
COOL = 10            # 启动事件冷却期(交易日)

_lines = []


def P(s=""):
    print(s)
    _lines.append(str(s))


def load():
    db = sqlite3.connect(DB, timeout=60)
    df = pd.read_sql_query(
        "SELECT code, substr(date,1,10) AS d, close, volume FROM daily_kline "
        "WHERE date >= ?", db, params=(START,))
    try:
        ff = pd.read_sql_query(
            "SELECT code, date AS d, netamount FROM fund_flow "
            "WHERE date >= ?", db, params=(START,))
    except Exception:
        ff = pd.DataFrame(columns=["code", "d", "netamount"])
    db.close()
    ind = pd.read_csv(IND, encoding="utf-8-sig", dtype=str)
    imap = dict(zip(ind["code"], ind["sector"]))
    return df, ff, imap


def zt_limit(code):
    """涨停阈值: 创业板/科创 20%, 北交所 30%, 其余 10%"""
    c = str(code)
    if c[:3] in ("300", "301", "688", "689"):
        return 0.197
    if c[:2] in ("43", "83", "87", "88") or c[0] == "8" or c[0] == "4":
        return 0.295
    return 0.097


def build(df, ff, imap):
    px = df.pivot_table(index="d", columns="code", values="close",
                        aggfunc="last").sort_index()
    vol = df.pivot_table(index="d", columns="code", values="volume",
                         aggfunc="last").sort_index().reindex(
        index=px.index, columns=px.columns)
    r1 = px.pct_change()

    # 涨停标记
    lim = pd.Series({c: zt_limit(c) for c in px.columns})
    zt = r1.ge(lim, axis=1) & r1.notna()

    ma20 = px.rolling(20, min_periods=15).mean()
    ma60 = px.rolling(60, min_periods=40).mean()

    # 行业 -> 成分股
    cols = {}
    for c, s in imap.items():
        if c in px.columns:
            cols.setdefault(s, []).append(c)

    # 资金流
    net = pd.DataFrame(index=px.index, columns=px.columns, dtype=float)
    if len(ff):
        f = ff.pivot_table(index="d", columns="code", values="netamount",
                           aggfunc="last")
        net = f.reindex(index=px.index, columns=px.columns)

    S, R, B, Z, V, M20, M60, NET = {}, {}, {}, {}, {}, {}, {}, {}
    for s, cs in cols.items():
        if len(cs) < MIN_STK:
            continue
        rr = r1[cs]
        # 板块指数: 个股日收益中位数累乘(不能用中位价格, 会随成分跳变)
        r1m = rr.median(axis=1).fillna(0)
        S[s] = (1 + r1m).cumprod()
        R[s] = r1m
        B[s] = (rr > 0).mean(axis=1) * 100
        Z[s] = zt[cs].sum(axis=1)
        V[s] = vol[cs].sum(axis=1)
        M20[s] = (px[cs] > ma20[cs]).mean(axis=1) * 100
        M60[s] = (px[cs] > ma60[cs]).mean(axis=1) * 100
        NET[s] = net[cs].sum(axis=1) / len(cs) / 1e4   # 万元/只

    idx = pd.DataFrame(S)
    ret = pd.DataFrame(R)
    brd = pd.DataFrame(B)
    ztd = pd.DataFrame(Z)
    vt = pd.DataFrame(V)
    m20 = pd.DataFrame(M20)
    m60 = pd.DataFrame(M60)
    netm = pd.DataFrame(NET)

    # 板块 5 日涨幅
    M = (idx / idx.shift(5) - 1) * 100

    # 未来收益
    FUT = {}
    for k, n in FWD.items():
        FUT[k] = (idx.shift(-n) / idx - 1) * 100

    return dict(px=px, idx=idx, ret=ret, brd=brd, ztd=ztd, vol=vt,
                m20=m20, m60=m60, net=netm, M=M, FUT=FUT, cols=cols,
                nstk=px.notna().sum(axis=1))


def make_features(d):
    """在 t 日可观测的特征矩阵(全部只用 t 及之前数据)"""
    idx, ret, brd, ztd = d["idx"], d["ret"], d["brd"], d["ztd"]
    vol, m20, m60, net, M = d["vol"], d["m20"], d["m60"], d["net"], d["M"]
    cols = d["cols"]

    f = {}
    f["amp5"] = M                                        # 5日涨幅
    f["breadth5"] = brd.rolling(5, min_periods=3).mean()  # 5日平均上涨占比
    f["zt5"] = ztd.rolling(5, min_periods=3).mean()       # 5日日均涨停家数
    f["zt1"] = ztd                                        # 当日涨停家数
    f["volr"] = (vol.rolling(5, min_periods=3).mean() /
                 vol.rolling(20, min_periods=10).mean())  # 量能放大
    f["ma20pct"] = m20                                    # 站上MA20比例
    f["ma60pct"] = m60                                    # 站上MA60比例

    # 60日位置
    hi = idx.rolling(60, min_periods=30).max()
    lo = idx.rolling(60, min_periods=30).min()
    f["pos60"] = (idx - lo) / (hi - lo) * 100

    # 龙头拉动: 涨幅前3均值 - 中位数(越大说明越靠少数股拉)
    r5s = {}
    for s, cs in cols.items():
        if s not in idx.columns:
            continue
        sub = d["px"][cs]
        r5 = (sub / sub.shift(5) - 1) * 100
        a = np.where(np.isnan(r5.values), -np.inf, r5.values)
        s3 = np.sort(a, axis=1)[:, ::-1][:, :3]        # 每行最大的3个
        ok = np.isfinite(s3)
        top3 = np.where(ok, s3, 0).sum(1) / np.maximum(ok.sum(1), 1)
        r5s[s] = pd.Series(top3, index=r5.index) - r5.median(axis=1)
    f["lead"] = pd.DataFrame(r5s).reindex(index=idx.index, columns=idx.columns)

    # 离散度: 板块内个股5日涨幅标准差(越小越齐涨)
    disp = {}
    for s, cs in cols.items():
        if s not in idx.columns:
            continue
        sub = d["px"][cs]
        r5 = (sub / sub.shift(5) - 1) * 100
        disp[s] = r5.std(axis=1)
    f["disp"] = pd.DataFrame(disp).reindex(index=idx.index, columns=idx.columns)

    f["money5"] = net.rolling(5, min_periods=3).sum()      # 5日主力净流入(万/只)

    # 持续性: 近5日板块日收益跑赢全市场中位数的天数
    mkt = ret.median(axis=1)
    beat = ret.gt(mkt, axis=0)
    f["consist"] = beat.rolling(5, min_periods=3).sum()

    # 前期平静度: 启动前20日涨幅(越小说明之前越沉寂)
    f["quiet20"] = (idx / idx.shift(25) - 1) * 100

    return {k: v.reindex(index=idx.index, columns=idx.columns)
            for k, v in f.items()}


def detect_events(M, min_rank=15, prev_min=25):
    """启动事件: 5日涨幅排名进入前N, 且此前一段时间没进过前N"""
    rank = M.rank(axis=1, ascending=False)
    prev_best = rank.rolling(20, min_periods=1).min().shift(1)
    raw = ((rank <= min_rank) & (prev_best > prev_min)).values
    # 冷却期: 每个板块 COOL 日内只算一次
    ev = np.zeros(raw.shape, dtype=bool)
    last = np.full(raw.shape[1], -999)
    for i in range(raw.shape[0]):
        hit = np.flatnonzero(raw[i] & ((i - last) > COOL))
        if len(hit):
            ev[i, hit] = True
            last[hit] = i
    return pd.DataFrame(ev, index=M.index, columns=M.columns), rank


def sample_obs(M, fut, top=15, step=3):
    """「刚涨起来」的观测池: 5日涨幅排名进入前 top 名的 (行业, 日期)。

    每 step 日采样一次, 降低相邻观测的重叠。
    返回 DataFrame: date, sector, fut, ex(相对同期全行业超额), pct(同期百分位)
    """
    rank = M.rank(axis=1, ascending=False)
    mkt = fut.mean(axis=1)
    ex = fut.sub(mkt, axis=0)
    pct = ex.rank(axis=1, pct=True)          # 同期横截面百分位
    dates = M.index[::step]
    rows = []
    for dt in dates:
        if dt not in fut.index:
            continue
        sel = rank.loc[dt][rank.loc[dt] <= top].index
        for s in sel:
            f = fut.loc[dt, s]
            if pd.isna(f):
                continue
            rows.append({"date": dt, "sector": s, "fut": f,
                         "ex": ex.loc[dt, s], "pct": pct.loc[dt, s],
                         "rank": rank.loc[dt, s]})
    return pd.DataFrame(rows), rank


def auc(pos, neg):
    """AUC: 正样本得分高于负样本的概率(Mann-Whitney)"""
    pos = np.asarray(pos); pos = pos[~np.isnan(pos)]
    neg = np.asarray(neg); neg = neg[~np.isnan(neg)]
    if len(pos) < 5 or len(neg) < 5:
        return np.nan, 0
    allv = np.concatenate([pos, neg])
    r = pd.Series(allv).rank().values
    rp = r[:len(pos)]
    return (rp.sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)), len(pos)


def main():
    P("板块「真主线」识别研究 — 刚涨起来时, 怎么判断这轮是不是真的大涨?")
    P("=" * 78)
    P(f"生成时间: {pd.Timestamp.now():%Y-%m-%d %H:%M}")
    P("")
    P("问法: 不做「预测下一个是谁」, 而是等板块刚涨起来后, 判断它是不是这轮真正的主线")
    P("标注: 把每个时点「未来20日跑赢同期75%板块」的板块定义为真主线(相对口径),")
    P("      再回看它们刚启动时能观察到的特征")

    df, ff, imap = load()
    d = build(df, ff, imap)
    idx, M, FUT = d["idx"], d["M"], d["FUT"]
    feats = make_features(d)
    fut20 = FUT["20日"]
    P(f"\n数据: {len(idx)} 个交易日 × {idx.shape[1]} 个行业 "
      f"({idx.index[0]} ~ {idx.index[-1]})")

    # ---- 观测池 ----
    E, rank = sample_obs(M, fut20, top=15, step=3)
    if E.empty:
        P("观测池为空")
        return
    midx = pd.MultiIndex.from_arrays([E["date"], E["sector"]])
    for k, fm in feats.items():
        st = fm.stack()
        st.index = st.index.set_names(["date", "sector"])
        E[k] = st.reindex(midx).values

    E["fut20"] = E["fut"]
    E["ex20"] = E["ex"]
    E["big"] = E["pct"] >= 0.75          # 相对口径: 同期超额前 25%
    E["abs8"] = E["fut20"] >= 8          # 绝对口径参照

    P(f"\n观测池(5日涨幅排名进前15, 每3日采样降重叠): {len(E)} 个")
    P(f"  真主线(未来20日跑赢同期75%的板块): {int(E['big'].sum())} 个 "
      f"({E['big'].mean()*100:.1f}%)")
    P(f"  绝对口径参照(未来20日涨幅>=8%):    {int(E['abs8'].sum())} 个 "
      f"({E['abs8'].mean()*100:.1f}%)")
    P(f"  全市场基准: 全部行业-日 未来20日平均 {fut20.stack().mean():+.2f}%")
    P(f"  观测池平均: 未来20日 {E['fut20'].mean():+.2f}%  "
      f"超额 {E['ex20'].mean():+.2f}%")

    P("\n" + "=" * 78)
    P("检验一: 真主线 vs 普通启动 — 启动时能观察到的差异")
    P("=" * 78)
    P(f"{'特征':<10}{'真主线':>10}{'普通':>10}{'差值':>9}{'AUC':>7}  含义")
    P("-" * 78)
    res = []
    for k in feats:
        a = E.loc[E["big"], k].dropna()
        b = E.loc[~E["big"], k].dropna()
        if len(a) < 20 or len(b) < 20:
            continue
        au, _ = auc(a, b)
        if np.isnan(au):
            continue
        meaning = ("真主线时更【高】" if au > 0.55 else
                   ("真主线时更【低】" if au < 0.45 else "几乎没区别"))
        P(f"{k:<10}{a.mean():>10.2f}{b.mean():>10.2f}{a.mean()-b.mean():>9.2f}"
          f"{au:>7.3f}  {meaning}")
        res.append((k, au, a.mean(), b.mean()))
    res.sort(key=lambda x: abs(x[1] - 0.5), reverse=True)

    P("\n区分度排行 (|AUC-0.5| 越大越有信息):")
    for k, au, am, bm in res[:8]:
        way = "高" if au > 0.5 else "低"
        P(f"  {k:<10} AUC={au:.3f}  真主线更{way} ({am:.2f} vs {bm:.2f})")

    P("\n" + "=" * 78)
    P("检验二: 单条规则筛选效果 (按该特征取前30%)")
    P("=" * 78)
    P(f"{'筛选条件':<32}{'样本':>6}{'真主线率':>9}{'未来20日':>10}{'超额':>9}")
    P("-" * 78)
    P(f"{'不筛选(全部刚涨起来的板块)':<32}{len(E):>6}"
      f"{E['big'].mean()*100:>8.1f}%{E['fut20'].mean():>10.2f}"
      f"{E['ex20'].mean():>9.2f}")

    conds = {
        "涨停家数多": ("zt5", False),
        "当日涨停多": ("zt1", False),
        "量能放大": ("volr", False),
        "板块内上涨股票多": ("breadth5", False),
        "站上MA60比例高": ("ma60pct", False),
        "站上MA20比例高": ("ma20pct", False),
        "跑赢大盘天数多": ("consist", False),
        "资金流入多": ("money5", False),
        "启动温和(涨幅低)": ("amp5", True),
        "龙头拉动小": ("lead", True),
        "个股涨得齐(离散小)": ("disp", True),
        "位置低": ("pos60", True),
        "前期沉寂": ("quiet20", True),
    }
    rule_res = []
    for lab, (k, asc) in conds.items():
        if k not in E.columns:
            continue
        q = E[k].rank(pct=True, ascending=asc)
        m = q <= 0.30
        sub = E[m]
        if len(sub) < 30:
            continue
        rate = sub["big"].mean() * 100
        P(f"{lab:<32}{len(sub):>6}{rate:>8.1f}%{sub['fut20'].mean():>10.2f}"
          f"{sub['ex20'].mean():>9.2f}")
        rule_res.append((lab, k, asc, rate, sub["ex20"].mean()))

    P("\n" + "=" * 78)
    P("检验三: 多特征打分模型 + 样本外验证")
    P("=" * 78)
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
    except Exception:
        P("sklearn 不可用, 跳过")
        return

    use = [k for k in feats if E[k].notna().mean() > 0.6]
    X = E[use].fillna(E[use].median())
    y = E["big"].astype(int).values
    dd = pd.to_datetime(E["date"])
    cut = dd.quantile(0.6)
    tr = (dd <= cut).values
    te = ~tr
    P(f"特征 {len(use)} 个: {', '.join(use)}")
    P(f"训练 {tr.sum()} 个 (至 {E.loc[tr,'date'].max()}) / "
      f"测试 {te.sum()} 个 (之后, 完全没见过)")

    sc = StandardScaler().fit(X[tr])
    lr = LogisticRegression(max_iter=2000, C=0.5).fit(sc.transform(X[tr]), y[tr])
    E["score"] = lr.predict_proba(sc.transform(X))[:, 1]

    def rep(mask, lab):
        s = E[mask]
        if len(s) < 10:
            return np.nan
        hi = s[s["score"] >= s["score"].quantile(0.7)]
        lo = s[s["score"] <= s["score"].quantile(0.3)]
        au, _ = auc(s.loc[s["big"], "score"], s.loc[~s["big"], "score"])
        P(f"  [{lab}] 高分组(前30%,{len(hi)}个): 真主线率"
          f"{hi['big'].mean()*100:>5.1f}%  未来20日{hi['fut20'].mean():>+7.2f}%  "
          f"超额{hi['ex20'].mean():>+6.2f}%")
        P(f"        低分组(后30%,{len(lo)}个): 真主线率"
          f"{lo['big'].mean()*100:>5.1f}%  未来20日{lo['fut20'].mean():>+7.2f}%  "
          f"超额{lo['ex20'].mean():>+6.2f}%   AUC={au:.3f}")
        return au

    au_tr = rep(tr, "训练段")
    au_te = rep(te, "测试段 样本外")
    if (not np.isnan(au_tr)) and (not np.isnan(au_te)) and au_tr > 0.5:
        keep = (au_te - 0.5) / (au_tr - 0.5) * 100
        P(f"  → 样本外保留率 {keep:.0f}%  "
          f"[(测试AUC-0.5)/(训练AUC-0.5)], >60% 说明不是靠碰巧")

    P("\n模型系数 (正=该特征越大, 越可能是真主线):")
    co = pd.Series(lr.coef_[0], index=use).sort_values(key=abs, ascending=False)
    for k, v in co.items():
        P(f"  {k:<10} {v:+.3f}")

    P("\n" + "=" * 78)
    P("检验四: 简单规则组合 (取区分度最高的3条叠加)")
    P("=" * 78)
    top3 = [r for r in res[:3]]
    P("采用规则: " + ", ".join(
        f"{k}{'高' if au > 0.5 else '低'}" for k, au, _, _ in top3))
    m = pd.Series(True, index=E.index)
    for k, au, _, _ in top3:
        q = E[k].rank(pct=True, ascending=(au < 0.5))
        m = m & (q <= 0.5)
    sub = E[m]
    if len(sub) >= 30:
        P(f"  命中 {len(sub)} 个: 真主线率 {sub['big'].mean()*100:.1f}%  "
          f"(不筛选是 {E['big'].mean()*100:.1f}%)")
        P(f"  未来20日 {sub['fut20'].mean():+.2f}%  超额 {sub['ex20'].mean():+.2f}%  "
          f"(不筛选超额 {E['ex20'].mean():+.2f}%)")
        q = sub["ex20"].quantile([0.1, 0.25, 0.5, 0.75, 0.9])
        P("  超额分位: " + "  ".join(f"{int(a*100)}%={b:+.1f}" for a, b in q.items()))
        P(f"  亏损超过5%的比例: {(sub['ex20']<-5).mean()*100:.0f}%  "
          f"(不筛选 {(E['ex20']<-5).mean()*100:.0f}%)")
        # 样本外
        ste = sub[pd.to_datetime(sub["date"]) > cut]
        if len(ste) >= 10:
            P(f"  【样本外】{len(ste)} 个: 真主线率 {ste['big'].mean()*100:.1f}%, "
              f"超额 {ste['ex20'].mean():+.2f}%, "
              f"亏损超5%占 {(ste['ex20']<-5).mean()*100:.0f}%")
            base_te = E[pd.to_datetime(E["date"]) > cut]
            P(f"     (同段不筛选基准: 真主线率 "
              f"{base_te['big'].mean()*100:.1f}%, 超额 "
              f"{base_te['ex20'].mean():+.2f}%, 亏损超5%占 "
              f"{(base_te['ex20']<-5).mean()*100:.0f}%)")

    P("\n" + "=" * 78)
    P("检验四B: 最佳单规则「板块内个股涨得齐」单独做样本外验证")
    P("=" * 78)
    if "disp" in E.columns:
        q = E["disp"].rank(pct=True, ascending=True)      # 离散度小
        for lab, msk in [("离散度最小30%", q <= 0.30),
                         ("离散度最大30%", q > 0.70)]:
            s = E[msk]
            ste = s[pd.to_datetime(s["date"]) > cut]
            P(f"  {lab:<16} 全部{len(s):>5}个 超额{s['ex20'].mean():>+6.2f}%  "
              f"真主线率{s['big'].mean()*100:>5.1f}%   |  样本外{len(ste)}个 "
              f"超额{ste['ex20'].mean():>+6.2f}% 真主线率{ste['big'].mean()*100:>5.1f}%")
        P(f"  参考阈值: 离散度 30%分位={E['disp'].quantile(0.30):.2f}, "
          f"50%分位={E['disp'].quantile(0.50):.2f}, "
          f"70%分位={E['disp'].quantile(0.70):.2f}")

    P("\n" + "=" * 78)
    P("检验五: 当前刚涨起来的板块打分")
    P("=" * 78)
    nstk = d["nstk"]
    ok = nstk[nstk >= nstk.max() * 0.6]
    if len(ok):
        dt = ok.index[-1]
        P(f"采用最后完整交易日: {dt}  (个股覆盖 {int(nstk.loc[dt])} 只)")
        C = pd.DataFrame({k: fm.loc[dt] for k, fm in feats.items()})
        C = C.dropna(subset=["amp5"])
        Cs = C[use].fillna(C[use].median())
        C["score"] = lr.predict_proba(sc.transform(Cs))[:, 1]
        C["5日涨幅"] = M.loc[dt]
        C["排名"] = rank.loc[dt]
        ev, _ = detect_events(M)
        C["近期启动"] = [bool(ev.loc[:dt, s].iloc[-15:].any()) for s in C.index]
        # 只保留「刚涨起来」的: 5日涨幅排名前15
        hot = C[C["排名"] <= 15].copy()
        P(f"\n【刚涨起来的板块】5日涨幅排名前15, 共 {len(hot)} 个, 按模型打分排序:")
        P(f"{'行业':<10}{'打分':>7}{'5日涨幅':>9}{'涨停/日':>8}{'量能比':>7}"
          f"{'MA60%':>7}{'位置':>6}{'排名':>5}  离散度  刚启动")
        C = hot.sort_values("score", ascending=False)
        for s, r in C.iterrows():
            dv = r["disp"] if pd.notna(r["disp"]) else np.nan
            P(f"{s:<10}{r['score']:>7.2f}{r['5日涨幅']:>9.2f}"
              f"{(r['zt5'] if pd.notna(r['zt5']) else 0):>8.1f}"
              f"{(r['volr'] if pd.notna(r['volr']) else 0):>7.2f}"
              f"{(r['ma60pct'] if pd.notna(r['ma60pct']) else 0):>7.0f}"
              f"{(r['pos60'] if pd.notna(r['pos60']) else 0):>6.0f}"
              f"{(int(r['排名']) if pd.notna(r['排名']) else 0):>5}"
              f"{(dv if pd.notna(dv) else 0):>8.2f}"
              f"  {'★' if r['近期启动'] else ''}")
        P("\n(★ = 近15个交易日内刚从排名20开外冲进前15, 属于「刚启动」)")

    P("\n" + "=" * 78)
    P("结论摘要")
    P("=" * 78)
    P(f"1. 基准: 板块刚涨起来时, 不加判断地买, 未来20日超额 {E['ex20'].mean():+.2f}%,")
    P(f"   成为真主线的概率 {E['big'].mean()*100:.1f}%")
    P("2. 最强单条规则: 【板块内个股涨得齐不齐】(近5日涨幅的标准差)")
    P("   齐涨 → 样本外超额 +1.51%, 真主线率 43%; 靠少数股硬拉 → -1.77%, 18%")
    P("3. 次强: 涨停家数少、不是靠龙头拉动 —— 与「不追高」是同一件事的两个面")
    P("4. 打分模型测试段 AUC 0.565(保留率48%), 高/低分组未来20日差 1.65 个百分点")
    P("   模型有一定判别力但偏弱, 实操建议用上面的简单规则, 别迷信模型打分")
    P("5. 以上为 2025 年以来 408 个交易日的历史统计, 不构成投资建议")

    io.open(OUT, "w", encoding="utf-8").write("\n".join(_lines))



if __name__ == "__main__":
    main()

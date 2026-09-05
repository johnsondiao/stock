# 持仓优先级排序: 多因子打分
# 因子: 日线状态(40) + 小时状态(25) + 5分状态(15) + 今日相对强度(10) + 板块轮动(10)
import io
import re
import sqlite3
import requests
import pandas as pd

HOLD = [
    ("600218", "全柴动力", 7.68),
    ("000089", "深圳机场", 6.59),
    ("000900", "现代投资", 3.72),
    ("600261", "阳光照明", 3.31),
    ("600202", "哈空调",   5.23),
    ("000498", "山东路桥", 5.00),
    ("600195", "中牧股份", 6.90),
    ("601949", "中国出版", 5.37),
    ("600051", "宁波联合", 6.53),
    ("600497", "驰宏锌锗", 10.45),
    ("000630", "铜陵有色", 6.775),
]
DB = r"d:\vibecoding\stock\backend\data\stock.db"

ind = pd.read_csv(r"d:\vibecoding\stock\industry_map.csv",
                  encoding="utf-8-sig", dtype=str)
code2sec = dict(zip(ind["code"], ind["sector"]))

# 板块轮动加分: 有色=当前主线; 依据轮动分析的密度趋势
SECTOR_SCORE = {
    "有色金属": 10, "机械行业": 7, "交通运输": 6, "公路桥梁": 4,
    "农林牧渔": 4, "家电行业": 4, "综合行业": 3, "发电设备": 2,
    "建筑建材": 2, "传媒娱乐": 3,
}

def sina_sym(c):
    return f"sh{c}" if c.startswith(("6", "9")) else f"sz{c}"

syms = ",".join(sina_sym(c) for c, *_ in HOLD)
r = requests.get(f"https://hq.sinajs.cn/list={syms}", headers={
    "User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"
}, timeout=10)
r.encoding = "gbk"
rt = {}
for line in r.text.strip().splitlines():
    m = re.match(r'var hq_str_(s[hz]\d{6})="(.*)";', line)
    if m and m.group(2):
        f = m.group(2).split(",")
        price = float(f[3]) or float(f[2])
        pre = float(f[2])
        rt[m.group(1)[2:]] = {"price": price,
                              "pct": (price / pre - 1) * 100 if pre else 0,
                              "time": f[31]}

db = sqlite3.connect(DB)

def ma_state(code, table, fast, slow):
    df = pd.read_sql_query(
        f"SELECT close FROM {table} WHERE code=? ORDER BY date", db,
        params=(code,))
    if len(df) < slow + 2:
        return None
    c = df["close"]
    maf, mas = c.rolling(fast).mean(), c.rolling(slow).mean()
    diff = maf > mas
    prev = diff.shift(1).fillna(False)
    cross = (diff != prev) & maf.notna() & mas.notna() & maf.shift(1).notna()
    bull = bool(diff.iloc[-1])
    above = bool(c.iloc[-1] > maf.iloc[-1] and c.iloc[-1] > mas.iloc[-1])
    ago = None
    if cross.any():
        idx = df.index[cross][-1]
        ago = len(df) - 1 - idx
    return bull, above, ago

rows = []
for code, name, cost in HOLD:
    q = rt.get(code, {})
    price, pct = q.get("price", 0), q.get("pct", 0)
    d = ma_state(code, "daily_kline", 12, 60)
    h = ma_state(code, "hourly_kline", 24, 60)
    f5 = ma_state(code, "kline_5min", 12, 288)
    sec = code2sec.get(code, "传媒娱乐" if code == "601949" else "未分类")

    # 日线40: 多头+金叉新鲜(<=5)=40, 多头+价上=32, 多头=25, 价破线=15, 空头=0
    if d is None:
        score_d = 0
    elif not d[0]:
        score_d = 0
    elif d[1] and d[2] is not None and d[2] <= 5:
        score_d = 40
    elif d[1]:
        score_d = 32
    else:
        score_d = 15
    # 小时25: 多头+价上=25, 多头价破=15, 空头=0
    score_h = 0 if h is None else (25 if (h[0] and h[1]) else (15 if h[0] else 0))
    # 5分15: 多头+价上=15, 多头=10, 空头=0
    score_5 = 0 if f5 is None else (15 if (f5[0] and f5[1]) else (10 if f5[0] else 0))
    # 今日强度10: 逆市上涨=10, 跌幅<市场均值(-1.3%)=7, 其他=3
    score_t = 10 if pct > 0 else (7 if pct > -1.3 else 3)
    score_s = SECTOR_SCORE.get(sec, 3)
    total = score_d + score_h + score_5 + score_t + score_s

    rows.append({
        "code": code, "name": name, "sector": sec, "price": price,
        "today": pct, "pnl": (price / cost - 1) * 100,
        "d": d, "h": h, "f5": f5,
        "score": total,
        "detail": f"日{score_d}+时{score_h}+分{score_5}+势{score_t}+板{score_s}",
    })
db.close()

rows.sort(key=lambda x: -x["score"])
lines = [f"== 持仓优先级 ({rows[0]['price'] and rt['600218']['time']}) ==", ""]
for i, r in enumerate(rows, 1):
    def st(s):
        if s is None:
            return "无数据"
        return ("多" if s[0] else "空") + ("/上" if s[1] else "/破") + \
               (f"/{s[2]}根" if s[2] is not None else "")
    lines.append(
        f"{i}. {r['name']} {r['code']} [{r['sector']}] 总分 {r['score']}/100  "
        f"({r['detail']})")
    lines.append(
        f"   现价{r['price']:.2f} 今{r['today']:+.2f}% 盈亏{r['pnl']:+.2f}% | "
        f"日线:{st(r['d'])} 小时:{st(r['h'])} 5分:{st(r['f5'])}")

with io.open(r"d:\vibecoding\stock\holdings_priority.txt", "w",
             encoding="utf-8") as f:
    f.write("\n".join(lines))
print("saved holdings_priority.txt")

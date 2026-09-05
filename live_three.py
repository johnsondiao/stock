# 三只争议持仓的最新实时行情 + 按真实成本重算盈亏
import io
import re
import requests

HEAD = {"User-Agent": "Mozilla/5.0",
        "Referer": "https://finance.sina.com.cn"}
# (代码, 名称, 券商截图成本)
HOLD = [("sh601949", "中国出版", 7.63),
        ("sh600202", "哈空调", 8.32),
        ("sz000498", "山东路桥", 8.47)]

r = requests.get(
    "https://hq.sinajs.cn/list=" + ",".join(s for s, *_ in HOLD),
    headers=HEAD, timeout=10)
r.encoding = "gbk"

out = io.open(r"d:\vibecoding\stock\live_three.txt", "w", encoding="utf-8")
costs = {sym: c for sym, _, c in HOLD}
names = {sym: n for sym, n, _ in HOLD}
for line in r.text.strip().splitlines():
    m = re.match(r'var hq_str_(\w+)="(.*)";', line)
    if not m or not m.group(2):
        continue
    sym, f = m.group(1), m.group(2).split(",")
    price, pre = float(f[3]), float(f[2])
    pct = (price / pre - 1) * 100 if pre else 0
    cost = costs[sym]
    pnl = (price / cost - 1) * 100
    out.write(f"{names[sym]} {sym[2:]}: 最新 {price:.2f} 今日{pct:+.2f}% "
              f"({f[30]} {f[31]}) | 成本 {cost} → 实际盈亏 {pnl:+.1f}%\n")
out.close()
print("done")

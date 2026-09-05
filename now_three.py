import io
import re
import requests

r = requests.get("https://hq.sinajs.cn/list=sz000630,sh600497,sh600218",
                 headers={"User-Agent": "Mozilla/5.0",
                          "Referer": "https://finance.sina.com.cn"}, timeout=8)
r.encoding = "gbk"
lines = []
for m in re.finditer(r'hq_str_(\w+)="([^"]+)"', r.text):
    f = m.group(2).split(",")
    price, pre = float(f[3]), float(f[2])
    pct = (price / pre - 1) * 100 if pre else 0
    lines.append(f"{f[0]} {m.group(1)[2:]}: 现价{price} ({pct:+.2f}%) "
                 f"今开{f[1]} 最高{f[4]} 最低{f[5]} 昨收{pre} @{f[31]}")
with io.open(r"d:\vibecoding\stock\now_three.txt", "w", encoding="utf-8") as fp:
    fp.write("\n".join(lines))
print("done")

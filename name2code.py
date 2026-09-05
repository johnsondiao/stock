# 按股票名查真实代码 (新浪 suggest 接口)
import io
import requests

names = ["哈空调", "山东路桥", "中国出版", "现代投资", "阳光照明", "中牧股份",
         "宁波联合", "兰花科创", "全柴动力"]
HEAD = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"}
out = io.open(r"d:\vibecoding\stock\name2code.txt", "w", encoding="utf-8")
for n in names:
    try:
        r = requests.get(
            f"https://suggest3.sinajs.cn/suggest/type=11,12&key={n}",
            headers=HEAD, timeout=8)
        r.encoding = "gbk"
        text = r.text.split('"')[1] if '"' in r.text else ""
        items = [x for x in text.split(";") if x][:4]
        parsed = []
        for it in items:
            f = it.split(",")
            if len(f) > 5:
                parsed.append(f"{f[3]}({f[2]})")
        out.write(f"{n}: {', '.join(parsed)}\n")
    except Exception as e:
        out.write(f"{n}: 查询失败 {e}\n")
out.close()
print("done")

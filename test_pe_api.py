# 验证新浪 Market_Center.getHQNodeData 的 pe/pb 字段
import re
import json
import requests

HEAD = {"User-Agent": "Mozilla/5.0",
        "Referer": "http://finance.sina.com.cn/"}
URL = ("http://vip.stock.finance.sina.com.cn/quotes_service/api/"
       "json_v2.php/Market_Center.getHQNodeData")

# 1. 总数
n = requests.get(URL.replace("getHQNodeData", "getHQNodeStockCount"),
                 params={"node": "hs_a"}, headers=HEAD, timeout=10)
print("hs_a 总数:", n.text)

# 2. 第1页3条, 只要 per/pb/price 字段
r = requests.get(URL, params={
    "page": 1, "num": 3, "sort": "symbol", "asc": 1,
    "node": "hs_a", "symbol": "", "_s_r_a": "page",
}, headers=HEAD, timeout=10)
fixed = re.sub(r'([{,])(\w+):', r'\1"\2":', r.text)
data = json.loads(fixed)
print("字段列表:", list(data[0].keys()))
for item in data:
    print(item["code"], item["name"], "价格", item["trade"],
          "PE", item.get("per"), "PB", item.get("pb"))

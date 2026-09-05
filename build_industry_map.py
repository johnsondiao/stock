# 直连新浪行业分类接口, 自行分页抓取全部成分股
import re
import time
import requests
import pandas as pd

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "http://finance.sina.com.cn/",
}
BASE = ("http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        "Market_Center.getHQNodeData")


def parse_sina_json(text: str) -> list:
    """新浪返回的是非标准JSON(键无引号), 手工修正后解析"""
    import json
    fixed = re.sub(r'([{,])(\w+):', r'\1"\2":', text)
    return json.loads(fixed)


def get_sectors() -> list:
    """获取新浪行业板块列表 [(label, 板块名)]"""
    import akshare as ak
    spot = ak.stock_sector_spot(indicator="新浪行业")
    name_col = [c for c in spot.columns if c != "label"][0]
    # 第二列是板块名
    return list(zip(spot["label"], spot.iloc[:, 1]))


rows = []
sectors = get_sectors()
print(f"板块数: {len(sectors)}")

for i, (label, sector) in enumerate(sectors, 1):
    got = 0
    for page in range(1, 30):  # 每页100条, 最多3000只/板块
        data, page_ok = [], False
        for attempt in range(3):
            try:
                r = requests.get(BASE, params={
                    "page": page, "num": 100, "sort": "symbol", "asc": 1,
                    "node": label, "symbol": "", "_s_r_a": "page",
                }, headers=HEADERS, timeout=10)
                text = r.text.strip()
                data = [] if text in ("null", "", "[]") else parse_sina_json(text)
                page_ok = True
                break
            except Exception as e:
                print(f"  [{sector}] p{page} 重试{attempt+1}: {e}")
                time.sleep(2)
        if not page_ok:
            break
        for item in data:
            code = str(item["code"]).zfill(6)
            rows.append((code, item["name"], sector))
        got += len(data)
        if len(data) < 100:
            break
        time.sleep(0.3)
    print(f"[{i}/{len(sectors)}] {sector}: {got} 只")

out = pd.DataFrame(rows, columns=["code", "name", "sector"]).drop_duplicates("code")
out.to_csv(r"d:\vibecoding\stock\industry_map.csv", index=False, encoding="utf-8-sig")
print(f"\n合计 {len(out)} 只, 板块数 {out['sector'].nunique()}")

import sqlite3
db = sqlite3.connect(r"d:\vibecoding\stock\backend\data\stock.db")
codes_db = {r[0] for r in db.execute("SELECT DISTINCT code FROM daily_kline")}
db.close()
mapped = codes_db & set(out["code"])
print(f"DB 股票 {len(codes_db)} 只, 命中行业映射 {len(mapped)} 只, 覆盖率 {len(mapped)/len(codes_db)*100:.1f}%")

# 尝试多种行业分类来源
import requests

# 方案1: akshare 新浪行业
try:
    import akshare as ak
    spot = ak.stock_sector_spot(indicator="新浪行业")
    print("新浪行业板块数:", len(spot), "列:", list(spot.columns))
    print(spot.head(3).to_string())
except Exception as e:
    print("akshare 新浪行业失败:", type(e).__name__, e)

# 方案2: 直连东财, 带浏览器UA
try:
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": 1, "pz": 5, "po": 1, "np": 1,
        "fltt": 2, "invt": 2, "fid": "f3",
        "fs": "m:90+t:2",  # 行业板块
        "fields": "f12,f14",
    }
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    r = requests.get(url, params=params, headers=headers, timeout=10)
    print("\n直连东财行业板块:", r.status_code, r.text[:200])
except Exception as e:
    print("\n直连东财失败:", type(e).__name__, e)

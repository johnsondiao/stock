"""下载全市场 15 分钟 K 线 (新浪 scale=15), 写入 kline_15min 表

15 分钟级分析需要长周期均线(如 MA240≈15个交易日 / MA960≈60个交易日),
本地 5 分钟数据只保留 12 个交易日, 远不够, 因此单独建一张 15 分钟表。

注: 原本为 ma_atr15 策略而建, 该策略已于 2026-09-08 移除,
    本表与下载器保留, 供后续 15 分钟级研究复用。

新浪 scale=15 单次最多约 1200 根 (≈75 个交易日), 故 datalen 取 1200。
不走全局 RateLimiter(30/分钟), 用独立并发池, 实测 6~10 只/秒。

用法:
    python kline15_download.py            # 全市场
    python kline15_download.py 600218     # 单只/多只调试
"""
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

DB = r"d:\vibecoding\stock\backend\data\stock.db"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://finance.sina.com.cn",
}
DATALEN = 1200
WORKERS = 8

_lock = threading.Lock()
_stat = {"ok": 0, "fail": 0, "rows": 0, "skip": 0}


def sina_symbol(code: str) -> str:
    if code.startswith(("6", "9")):
        return f"sh{code}"
    if code.startswith(("0", "3")):
        return f"sz{code}"
    return f"bj{code}"


def init_table():
    db = sqlite3.connect(DB, timeout=60)
    db.execute("""
        CREATE TABLE IF NOT EXISTS kline_15min (
            code TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL, volume REAL,
            PRIMARY KEY (code, date)
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS idx_k15_date ON kline_15min(date)")
    db.commit()
    db.close()


def fetch(code: str):
    """返回 (code, rows) rows=[[date,open,high,low,close,volume], ...]"""
    url = ("https://quotes.sina.cn/cn/api/json_v2.php/"
           f"CN_MarketDataService.getKLineData?symbol={sina_symbol(code)}"
           f"&scale=15&ma=no&datalen={DATALEN}")
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            data = r.json()
            if not isinstance(data, list) or not data:
                return code, []
            rows = []
            for d in data:
                try:
                    rows.append((d["day"], float(d["open"]), float(d["high"]),
                                 float(d["low"]), float(d["close"]),
                                 float(d["volume"])))
                except (KeyError, ValueError, TypeError):
                    continue
            return code, rows
        except Exception:
            if attempt == 2:
                return code, []
            time.sleep(0.6 * (attempt + 1))
    return code, []


def save(batch):
    if not batch:
        return
    db = sqlite3.connect(DB, timeout=60)
    try:
        db.executemany(
            "INSERT OR REPLACE INTO kline_15min "
            "(code,date,open,high,low,close,volume) VALUES (?,?,?,?,?,?,?)",
            batch)
        db.commit()
    finally:
        db.close()


def main():
    init_table()
    db = sqlite3.connect(DB, timeout=60)
    if len(sys.argv) > 1:
        codes = sys.argv[1:]
    else:
        codes = [r[0] for r in db.execute(
            "SELECT DISTINCT code FROM daily_kline").fetchall()]
    db.close()

    print(f"待下载 {len(codes)} 只, 并发 {WORKERS}, datalen={DATALEN}")
    t0 = time.time()
    batch = []

    def work(c):
        nonlocal batch
        code, rows = fetch(c)
        with _lock:
            if rows:
                _stat["ok"] += 1
                _stat["rows"] += len(rows)
                batch.extend((code, *r) for r in rows)
                if len(batch) >= 20000:
                    save(batch)
                    batch.clear()
            else:
                _stat["fail"] += 1
                print(f"  失败: {code}")
            n = _stat["ok"] + _stat["fail"]
            if n % 200 == 0:
                el = time.time() - t0
                print(f"  进度 {n}/{len(codes)}  成功{_stat['ok']} "
                      f"失败{_stat['fail']}  行{_stat['rows']}  "
                      f"{n/el:.1f}只/秒  预计剩余{(len(codes)-n)/(n/el)/60:.1f}分")

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        list(ex.map(work, codes))

    save(batch)
    el = time.time() - t0
    print(f"\n完成: 成功 {_stat['ok']}, 失败 {_stat['fail']}, "
          f"写入 {_stat['rows']} 行, 耗时 {el/60:.1f} 分钟")


if __name__ == "__main__":
    main()

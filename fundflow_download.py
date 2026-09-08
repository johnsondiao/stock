# -*- coding: utf-8 -*-
"""
下载全市场个股主力资金流历史 (新浪 MoneyFlow.ssl_qsfx_zjlrqs)

字段含义:
  netamount   主力净流入额(元, 超大单+大单)
  ratioamount 主力净流入占成交额比例
  r0_net      超大单净流入额
  turnover    换手率(万手/万股, 仅参考)

用法:
  python fundflow_download.py          # 全量(首次)
  python fundflow_download.py 60       # 只补最近60个交易日
"""
import os
import sys
import time
import json
import sqlite3
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

DB = r"d:\vibecoding\stock\backend\data\stock.db"
API = ("https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
       "MoneyFlow.ssl_qsfx_zjlrqs?page=1&num={n}&sort=opendate&asc=0&daima={sym}")
HEAD = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"}
WORKERS = 10


def init():
    db = sqlite3.connect(DB, timeout=60)
    db.execute("""
        CREATE TABLE IF NOT EXISTS fund_flow (
            code      TEXT NOT NULL,
            date      TEXT NOT NULL,
            netamount REAL,
            ratio     REAL,
            r0_net    REAL,
            close     REAL,
            pct       REAL,
            turnover  REAL,
            PRIMARY KEY (code, date)
        )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_ff_date ON fund_flow(date)")
    db.commit()
    return db


def get_codes():
    db = sqlite3.connect(DB, timeout=60)
    rows = db.execute("SELECT DISTINCT code FROM daily_kline WHERE date >= '2025-01-01'").fetchall()
    db.close()
    return [r[0] for r in rows]


def sym_of(code):
    return ("sh" if code[0] in "69" else "sz") + code


def fetch(sym, num):
    sess = requests.Session()
    sess.trust_env = False
    sess.headers.update(HEAD)
    for attempt in range(3):
        try:
            r = sess.get(API.format(n=num, sym=sym), timeout=20)
            if r.status_code != 200:
                time.sleep(1 + attempt)
                continue
            txt = r.text.strip()
            if not txt or txt in ("[]", "null"):
                return []
            return json.loads(txt)
        except Exception:
            time.sleep(1.5 + attempt * 1.5)
    return None


def main():
    num = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    db = init()
    codes = get_codes()
    print(f"待下载 {len(codes)} 只, 每只最多 {num} 个交易日")
    t0 = time.time()
    ok = fail = skip = 0
    done = 0
    lock_buf = []

    def flush(buf):
        if not buf:
            return
        db.executemany(
            "INSERT OR REPLACE INTO fund_flow VALUES (?,?,?,?,?,?,?,?)", buf)
        db.commit()

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(fetch, sym_of(c), num): c for c in codes}
        for fu in as_completed(futs):
            code = futs[fu]
            done += 1
            try:
                data = fu.result()
            except Exception:
                data = None
            if data is None:
                fail += 1
            elif not data:
                skip += 1
            else:
                ok += 1
                for it in data:
                    try:
                        lock_buf.append((
                            code, it["opendate"],
                            float(it.get("netamount") or 0),
                            float(it.get("ratioamount") or 0),
                            float(it.get("r0_net") or 0),
                            float(it.get("trade") or 0),
                            float(it.get("changeratio") or 0),
                            float(it.get("turnover") or 0),
                        ))
                    except (ValueError, TypeError):
                        continue
            if len(lock_buf) > 60000:
                flush(lock_buf)
                lock_buf.clear()
            if done % 200 == 0:
                el = time.time() - t0
                print(f"  {done}/{len(codes)}  成功{ok} 空{skip} 失败{fail}  "
                      f"{el:.0f}s  预计剩余 {el/done*(len(codes)-done):.0f}s")

    flush(lock_buf)
    n = db.execute("SELECT COUNT(*), COUNT(DISTINCT code), MAX(date) FROM fund_flow").fetchone()
    print(f"\n完成: 成功{ok} 无数据{skip} 失败{fail}  耗时 {time.time()-t0:.0f}s")
    print(f"fund_flow 表: {n[0]} 行 / {n[1]} 只 / 最新 {n[2]}")
    db.close()


if __name__ == "__main__":
    main()

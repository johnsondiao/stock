#!/usr/bin/env python3
"""
日线数据回填工具 (一次性)

背景:
  后台更新服务 data_updater 只维护 hourly_kline / kline_5min,
  遗漏了 daily_kline, 导致日线缓存长期冻结。
  本脚本用新浪 scale=240 接口一次性补齐缺口。

用法:
    python backfill_daily.py              # 增量补齐到最新交易日
    python backfill_daily.py --workers 8  # 指定并发数
    python backfill_daily.py --days 30    # 指定拉取根数(交易日)
"""

import argparse
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests

DB = r"d:\vibecoding\stock\backend\data\stock.db"
URL = ("https://vip.stock.finance.sina.com.cn/quotes_service/api/"
       "json_v2.php/CN_MarketData.getKLineData")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://finance.sina.com.cn",
}
MAX_CANDLES = 300          # 与 settings.kline_max_candles 保持一致
BATCH_COMMIT = 200         # 每 N 只提交一次


def sina_symbol(code: str) -> str:
    return f"sh{code}" if code.startswith(("6", "9")) else f"sz{code}"


def norm_date(day: str) -> str:
    """新浪返回 'YYYY-MM-DD', 统一为 'YYYY-MM-DD 00:00:00'"""
    return f"{day[:10]} 00:00:00"


def fetch_one(code: str, days: int, retries: int = 2) -> tuple[str, list[tuple] | None]:
    """拉取单只股票日线, 返回 (code, rows|None)"""
    for attempt in range(retries + 1):
        try:
            r = requests.get(URL, params={
                "symbol": sina_symbol(code), "scale": "240",
                "ma": "no", "datalen": days,
            }, headers=HEADERS, timeout=12)
            r.raise_for_status()
            items = r.json()
            if not items:
                return code, []
            rows = []
            for it in items:
                try:
                    rows.append((
                        code, norm_date(it["day"]),
                        float(it["open"]), float(it["high"]),
                        float(it["low"]), float(it["close"]),
                        float(it["volume"]),
                    ))
                except (KeyError, ValueError, TypeError):
                    continue
            return code, rows
        except Exception:
            if attempt == retries:
                return code, None
            time.sleep(1.5 * (attempt + 1))
    return code, None


def load_codes() -> list[str]:
    conn = sqlite3.connect(DB)
    try:
        return [r[0] for r in conn.execute(
            "SELECT DISTINCT code FROM daily_kline ORDER BY code")]
    finally:
        conn.close()


def write_back(all_rows: dict[str, list[tuple]], trim: bool) -> tuple[int, int]:
    """写回数据库, 返回 (更新股票数, 写入行数)"""
    conn = sqlite3.connect(DB, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    inserted = 0
    stocks = 0
    try:
        for i, (code, rows) in enumerate(all_rows.items(), 1):
            if not rows:
                continue
            conn.executemany(
                "INSERT INTO daily_kline (code, date, open, high, low, close, volume, amount) "
                "VALUES (?,?,?,?,?,?,?,0) "
                "ON CONFLICT(code, date) DO UPDATE SET "
                "open=excluded.open, high=excluded.high, low=excluded.low, "
                "close=excluded.close, volume=excluded.volume",
                rows,
            )
            inserted += len(rows)
            stocks += 1
            if trim:
                conn.execute(
                    "DELETE FROM daily_kline WHERE code=? AND date NOT IN ("
                    "  SELECT date FROM daily_kline WHERE code=? "
                    "  ORDER BY date DESC LIMIT ?)",
                    (code, code, MAX_CANDLES),
                )
            if i % BATCH_COMMIT == 0:
                conn.commit()
                print(f"  写入进度 {i}/{len(all_rows)} ...", flush=True)
        conn.commit()
    finally:
        conn.close()
    return stocks, inserted


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--days", type=int, default=30, help="每只拉取的交易日根数")
    ap.add_argument("--no-trim", action="store_true", help="不裁剪到 300 根")
    args = ap.parse_args()

    codes = load_codes()
    if not codes:
        print("daily_kline 为空, 请先跑 download_data.py")
        return 1

    before = sqlite3.connect(DB).execute(
        "SELECT MAX(date) FROM daily_kline").fetchone()[0]
    print(f"回填前最新日线: {before}")
    print(f"待处理 {len(codes)} 只, 并发 {args.workers}, 每只 {args.days} 根")
    print("开始拉取...", flush=True)

    t0 = time.time()
    all_rows: dict[str, list[tuple]] = {}
    failed: list[str] = []

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for n, (code, rows) in enumerate(
                ex.map(lambda c: fetch_one(c, args.days), codes), 1):
            if rows is None:
                failed.append(code)
            else:
                all_rows[code] = rows
            if n % 500 == 0 or n == len(codes):
                el = time.time() - t0
                print(f"  拉取 {n}/{len(codes)}  耗时 {el:.0f}s  "
                      f"速率 {n/el:.1f} 只/秒  失败 {len(failed)}", flush=True)

    el = time.time() - t0
    print(f"\n拉取完成: 成功 {len(all_rows)} / 失败 {len(failed)} / 耗时 {el:.0f}s")
    if failed:
        print(f"失败代码(前20): {failed[:20]}")
        print("串行重试中...", flush=True)
        for code in failed:
            _, rows = fetch_one(code, args.days, retries=3)
            if rows is not None:
                all_rows[code] = rows
                failed.remove(code)
            time.sleep(0.3)
        print(f"重试后仍失败: {len(failed)}")

    stocks, inserted = write_back(all_rows, trim=not args.no_trim)
    after = sqlite3.connect(DB).execute(
        "SELECT MAX(date) FROM daily_kline").fetchone()[0]

    print(f"\n写入完成: {stocks} 只股票, {inserted} 行")
    print(f"回填后最新日线: {after}")

    conn = sqlite3.connect(DB)
    print("\n最近 8 个交易日覆盖情况:")
    for d, cnt in conn.execute(
            "SELECT date, COUNT(*) FROM daily_kline "
            "GROUP BY date ORDER BY date DESC LIMIT 8"):
        print(f"  {d[:10]}  {cnt} 只")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

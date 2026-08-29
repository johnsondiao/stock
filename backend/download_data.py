#!/usr/bin/env python3
"""
全市场股票数据慢速下载器
- 只下载主板股票（沪市600-605、深市000-004）
- 排除创业板(300)、科创板(688)、北交所
- 慢速下载避免限流（利用全局令牌桶限流器）
- 增量更新：已有缓存的股票只拉取最新少量数据
- 数据保存到 SQLite 缓存，后续选股直接读缓存

用法:
    python download_data.py              # 正常增量下载（小时+日K线）
    python download_data.py --full       # 强制全量重新下载（忽略缓存）
    python download_data.py --hourly-only  # 只下载小时K线
    python download_data.py --daily-only   # 只下载日K线
"""

import sys
import time
import argparse
from pathlib import Path

# 确保 backend 目录在 sys.path 中
_backend_dir = str(Path(__file__).resolve().parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from app.log_config import setup_logging, get_logger
from app.database import init_db
from app.data.provider import get_provider
from app.data import cache
from app.data.rate_limiter import get_rate_limiter

setup_logging()
logger = get_logger("downloader")


def is_main_board(code: str) -> bool:
    """判断是否为主板股票（普通账户可交易）"""
    if code.startswith(("6",)):      # 沪市: 600-609 (含688科创板但会被行情过滤)
        return True
    if code.startswith(("0", "1", "2", "3")):
        # 深市 000-004: 主板/中小板 OK
        # 深市 300-301: 创业板 NO
        if code.startswith("3"):
            return False
        return True
    return False  # 4/8/9 开头: 北交所/三板/基金等


def fmt_time(seconds: float) -> str:
    """格式化时间为 Xh Xm"""
    if seconds < 60:
        return f"{seconds:.0f}秒"
    elif seconds < 3600:
        return f"{seconds / 60:.0f}分{seconds % 60:.0f}秒"
    else:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        return f"{h}时{m}分"


def _download_phase(label: str, fetcher, codes: list[str], force_full: bool) -> dict:
    """
    通用下载阶段：遍历代码列表调用 fetcher，返回统计
    :param label: 阶段名称（如 "小时K线"）
    :param fetcher: callable(code) -> DataFrame
    """
    total = len(codes)
    downloaded = 0
    skipped = 0
    errors = 0
    start_time = time.time()

    logger.info("[%s] 开始下载...", label)

    try:
        for i, code in enumerate(codes):
            try:
                df = fetcher(code)
                if df is not None and not df.empty:
                    downloaded += 1
                else:
                    skipped += 1
            except Exception as e:
                errors += 1
                if errors <= 30:
                    logger.warning("  [ERR] %s: %s", code, e)
                elif errors == 31:
                    logger.warning("  (后续错误不再逐条显示)")

            # 进度报告（每 10 只或最后一只）
            done = i + 1
            if done % 10 == 0 or done == total:
                elapsed = time.time() - start_time
                speed = done / elapsed if elapsed > 0 else 0
                remaining = (total - done) / speed if speed > 0 else 0
                logger.info(
                    "  %s [%d/%d] OK:%d ERR:%d SKIP:%d | 速度 %.1f只/分 | 剩余 ~%s",
                    label, done, total, downloaded, errors, skipped,
                    speed * 60, fmt_time(remaining)
                )

    except KeyboardInterrupt:
        logger.warning("\n[!] 用户中断 (Ctrl+C)")

    elapsed = time.time() - start_time
    logger.info("")
    logger.info("[%s] 下载完成:", label)
    logger.info("  OK: %d 只", downloaded)
    logger.info("  SKIP: %d 只", skipped)
    logger.info("  ERR: %d 只", errors)
    logger.info("  耗时: %s", fmt_time(elapsed))
    return {"ok": downloaded, "skip": skipped, "err": errors, "elapsed": elapsed}


def download(force_full: bool = False, hourly_only: bool = False, daily_only: bool = False):
    """主下载流程"""
    init_db()
    provider = get_provider()

    logger.info("=" * 60)
    logger.info("[下载器] 全市场数据下载器启动")
    logger.info("=" * 60)

    # ── 1. 缓存状态 ──
    stats = cache.get_cache_stats()
    logger.info("当前缓存: 小时K线 %d 只, 日K线 %d 只",
                stats["hourly_cached_stocks"], stats["daily_cached_stocks"])

    # ── 2. 获取全市场股票列表 ──
    logger.info("正在获取全市场股票列表...")
    all_stocks = provider.get_all_stocks(force_refresh=True)
    if all_stocks.empty:
        logger.error("[错误] 无法获取股票列表，请检查网络连接")
        return

    logger.info("全市场共 %d 只股票（含所有板块）", len(all_stocks))

    # ── 3. 过滤主板 ──
    main_board = all_stocks[all_stocks["code"].apply(is_main_board)].copy()
    logger.info("主板股票: %d 只（排除创业板/科创板/北交所）", len(main_board))

    codes = sorted(main_board["code"].tolist())
    cached_codes = cache.get_cached_codes("hourly_kline")

    if force_full:
        logger.info("[!] 强制全量模式：将重新下载所有 %d 只股票", len(codes))
    else:
        already_cached = [c for c in codes if c in cached_codes]
        need_full = [c for c in codes if c not in cached_codes]
        logger.info("  已有缓存: %d 只（增量更新）", len(already_cached))
        logger.info("  需要新下载: %d 只", len(need_full))

    total = len(codes)
    if total == 0:
        logger.info("[OK] 没有需要下载的股票")
        return

    # ── 4. 显示限流配置 ──
    limiter = get_rate_limiter()
    lim_info = limiter.get_stats()
    logger.info("限流配置: %d 请求/分钟", lim_info["rate_per_minute"])
    logger.info("-" * 60)

    start_time = time.time()

    # ── 5. 下载小时 K 线 ──
    if not daily_only:
        _download_phase("小时K线", provider.get_hourly_kline, codes, force_full)
    else:
        logger.info("[小时K线] 已跳过 (--daily-only)")

    # ── 6. 下载日 K 线 ──
    if not hourly_only:
        logger.info("")
        logger.info("-" * 60)
        _download_phase("日K线", provider.get_daily_kline, codes, force_full)
    else:
        logger.info("[日K线] 已跳过 (--hourly-only)")

    # ── 7. 最终汇总 ──
    final_stats = cache.get_cache_stats()
    total_time = time.time() - start_time
    logger.info("")
    logger.info("=" * 60)
    logger.info("[完成] 下载任务全部完成!")
    logger.info("  总耗时: %s", fmt_time(total_time))
    logger.info("  缓存中小时K线: %d 只股票", final_stats["hourly_cached_stocks"])
    logger.info("  缓存中日K线:   %d 只股票", final_stats["daily_cached_stocks"])
    logger.info("  数据库文件: %s", Path(_backend_dir) / "data" / "stock.db")
    logger.info("=" * 60)
    logger.info("[提示] 以后再次运行此脚本将自动增量下载，只更新最新数据")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="全市场股票数据慢速下载器")
    parser.add_argument("--full", action="store_true", help="强制全量重新下载（忽略缓存）")
    parser.add_argument("--hourly-only", action="store_true", help="只下载小时K线")
    parser.add_argument("--daily-only", action="store_true", help="只下载日K线")
    args = parser.parse_args()
    download(force_full=args.full, hourly_only=args.hourly_only, daily_only=args.daily_only)

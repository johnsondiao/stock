"""选股服务 - 后台任务 + 进度追踪 + 并发扫描"""

import json
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pandas as pd

from app.config import settings
from app.data.provider import get_provider
from app.data import cache
from app.strategy.base import Signal
from app.strategy import registry as strategy_registry
from app.log_config import get_logger

logger = get_logger(__name__)

# 内存中的任务进度（实时，供轮询用）
_task_progress: dict[str, dict] = {}
_lock = threading.Lock()


def start_screen(strategy_name: str, params: dict,
                 prefilter: dict | None = None) -> str:
    """
    启动选股任务（异步）

    :param strategy_name: 策略名称
    :param params: 策略参数
    :param prefilter: 预筛条件 {min_price, max_price, min_market_cap, exclude_st}
    :return: task_id
    """
    strategy = strategy_registry.get(strategy_name)
    if strategy is None:
        raise ValueError(f"未知策略: {strategy_name}")

    task_id = uuid.uuid4().hex[:12]

    # 初始化任务记录
    cache.save_screen_task(task_id, strategy_name, params, status="pending")
    with _lock:
        _task_progress[task_id] = {
            "status": "pending", "progress": 0, "total": 0,
            "matched": 0, "skipped": 0, "errors": 0,
        }

    # 启动后台线程执行
    t = threading.Thread(
        target=_run_screen_task,
        args=(task_id, strategy_name, params, prefilter or {}),
        daemon=True,
    )
    t.start()
    logger.info("选股任务已启动: task_id=%s, strategy=%s", task_id, strategy_name)
    return task_id


def get_task_status(task_id: str) -> dict | None:
    """查询任务状态和进度"""
    # 优先从内存获取实时进度
    with _lock:
        mem = _task_progress.get(task_id)

    db_task = cache.load_screen_task(task_id)
    if db_task is None and mem is None:
        return None

    result = db_task or {}
    if mem:
        result.update(mem)
    return result


def get_task_result(task_id: str) -> dict | None:
    """获取选股结果"""
    task = cache.load_screen_task(task_id)
    if not task or not task.get("result_json"):
        return None
    try:
        return json.loads(task["result_json"])
    except json.JSONDecodeError:
        return None


def list_tasks(limit: int = 20) -> list[dict]:
    """列出最近的选股任务"""
    return cache.list_screen_tasks(limit)


# ── 内部实现 ──────────────────────────────────────────────


def _update_progress(task_id: str, **kwargs):
    """更新任务进度（内存 + DB）"""
    with _lock:
        if task_id in _task_progress:
            _task_progress[task_id].update(kwargs)
        progress = _task_progress.get(task_id, {}).get("progress", 0)
        total = _task_progress.get(task_id, {}).get("total", 0)
        matched = _task_progress.get(task_id, {}).get("matched", 0)
        skipped = _task_progress.get(task_id, {}).get("skipped", 0)
        errors = _task_progress.get(task_id, {}).get("errors", 0)
        status = kwargs.get("status", "running")

    cache.save_screen_task(
        task_id,
        strategy=kwargs.get("strategy", ""),
        params=kwargs.get("params", {}),
        status=status,
        progress=progress,
        total=total,
        matched=matched,
        skipped=skipped,
        errors=errors,
    )


def _run_screen_task(task_id: str, strategy_name: str,
                     params: dict, prefilter: dict):
    """后台执行选股任务"""
    try:
        strategy = strategy_registry.get(strategy_name)
        provider = get_provider()

        _update_progress(task_id, status="running", strategy=strategy_name, params=params)

        # Step 1: 刷新行情快照
        logger.info("[%s] Step 1: 刷新行情快照...", task_id)
        snapshot = provider.get_all_stocks(force_refresh=True)
        if snapshot.empty:
            _update_progress(task_id, status="failed", progress=0)
            logger.error("[%s] 行情快照为空", task_id)
            return

        logger.info("[%s] 行情快照: %d 只股票", task_id, len(snapshot))

        # Step 2: 预筛选
        candidates = _apply_prefilter(snapshot, prefilter)
        logger.info("[%s] 预筛选后: %d 只候选 (排除 %d 只)",
                    task_id, len(candidates), len(snapshot) - len(candidates))

        # Step 3: 缓存预筛 - 利用已有K线缓存快速排除
        candidates, cache_skipped = _cache_prefilter(candidates, params)
        logger.info("[%s] 缓存预筛后: %d 只候选 (缓存排除 %d 只)",
                    task_id, len(candidates), cache_skipped)

        # Step 4: 并发获取K线 + 策略评估
        total = len(candidates)
        _update_progress(task_id, total=total, progress=0)

        results = []
        errors = 0
        processed = 0

        # 分批并发处理
        batch_size = settings.scan_batch_size
        for batch_start in range(0, total, batch_size):
            batch = candidates.iloc[batch_start:batch_start + batch_size]
            batch_results, batch_errors = _process_batch(
                task_id, batch, strategy, params, provider
            )
            results.extend(batch_results)
            errors += batch_errors
            processed += len(batch)

            _update_progress(
                task_id,
                progress=processed,
                matched=len(results),
                errors=errors,
            )

            logger.info("[%s] 进度: %d/%d, 匹配: %d, 错误: %d",
                        task_id, processed, total, len(results), errors)

            # 批次间暂停，避免 API 限流
            if batch_start + batch_size < total:
                import time
                time.sleep(settings.scan_batch_pause)

        # Step 5: 排序并保存结果
        results.sort(key=lambda x: (x.get("score", 0), x.get("above_count", 0)), reverse=True)

        result_data = {
            "strategy": strategy_name,
            "params": params,
            "total_scanned": total,
            "matched_count": len(results),
            "errors": errors,
            "cache_skipped": cache_skipped,
            "prefilter_skipped": len(snapshot) - len(candidates) - cache_skipped,
            "results": results,
            "completed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        _update_progress(
            task_id,
            status="completed",
            progress=total,
            matched=len(results),
            errors=errors,
        )
        cache.save_screen_task(
            task_id, strategy_name, params,
            status="completed", progress=total,
            matched=len(results), errors=errors,
            result_json=json.dumps(result_data, ensure_ascii=False, default=str),
        )

        logger.info("[%s] 选股完成: 扫描 %d 只, 匹配 %d 只, 错误 %d",
                    task_id, total, len(results), errors)

    except Exception as e:
        logger.exception("[%s] 选股任务异常: %s", task_id, e)
        _update_progress(task_id, status="failed")


def _apply_prefilter(df: pd.DataFrame, prefilter: dict) -> pd.DataFrame:
    """
    应用预筛选条件
    注意: 非交易时间 volume 可能为 0，不应排除
    """
    mask = pd.Series(True, index=df.index)

    # 排除 ST
    if prefilter.get("exclude_st", True):
        if "name" in df.columns:
            mask &= ~df["name"].str.contains("ST", case=False, na=False)

    # 价格区间
    min_price = prefilter.get("min_price")
    if min_price:
        mask &= df["price"] >= min_price
    max_price = prefilter.get("max_price")
    if max_price:
        mask &= df["price"] <= max_price

    # 最小市值（万元）—— 新浪接口不提供市值，跳过
    min_mv = prefilter.get("min_market_cap")
    if min_mv and "total_mv" in df.columns:
        # 只在有实际市值数据时才过滤
        if df["total_mv"].sum() > 0:
            mask &= df["total_mv"] >= min_mv

    # 排除停牌: 只在交易时间过滤（有成交量数据时）
    # 盘前/盘后 volume 全为 0，此时不过滤
    if "volume" in df.columns:
        has_volume = (df["volume"] > 0).sum()
        if has_volume > len(df) * 0.1:  # 超过 10% 的股票有成交量，说明是交易时间
            mask &= df["volume"] > 0

    return df[mask].reset_index(drop=True)


def _cache_prefilter(candidates: pd.DataFrame, params: dict) -> tuple:
    """
    利用缓存的K线数据快速预筛
    如果缓存中最新 MA169 远高于当前价格，则不可能站上全部均线
    """
    min_above = params.get("min_above", 4)
    if min_above < 4:
        return candidates, 0  # 要求不高，不做预筛

    passed = []
    skipped = 0

    for _, row in candidates.iterrows():
        code = row["code"]
        price = float(row.get("price", 0))

        cached = cache.load_kline(code, "hourly_kline")
        if cached.empty or len(cached) < 169:
            passed.append(row)  # 无缓存，保留候选
            continue

        # 计算缓存中的 MA169
        ma169 = cached["close"].tail(169).mean()
        # 如果价格低于 MA169 的 90%，基本不可能站上
        if price < ma169 * 0.90:
            skipped += 1
        else:
            passed.append(row)

    result_df = pd.DataFrame(passed) if passed else pd.DataFrame()
    return result_df, skipped


def _process_batch(task_id: str, batch: pd.DataFrame,
                   strategy, params: dict, provider) -> tuple:
    """处理一批候选股票（并发获取K线 + 评估策略）"""
    results = []
    errors = 0

    def _fetch_and_evaluate(row):
        code = row["code"]
        name = row.get("name", "")
        price = float(row.get("price", 0))
        pct = float(row.get("pct_change", 0))

        try:
            kline = provider.get_hourly_kline(code)
            if kline.empty or len(kline) < 170:
                return None

            eval_result = strategy.evaluate(kline, params)
            signal = eval_result.get("signal", Signal.NEUTRAL)
            score = eval_result.get("score", 0)
            details = eval_result.get("details", {})

            # 只返回满足条件的
            min_above = params.get("min_above", 4)
            above_count = details.get("above_count", 0)
            if above_count < min_above and score < 50:
                return None

            return {
                "code": code,
                "name": name,
                "price": price,
                "pct_change": pct,
                "signal": str(signal.value) if hasattr(signal, "value") else str(signal),
                "score": score,
                **details,
            }
        except Exception as e:
            logger.debug("处理 %s 失败: %s", code, e)
            return "error"

    with ThreadPoolExecutor(max_workers=settings.scan_max_workers) as executor:
        futures = {}
        for _, row in batch.iterrows():
            f = executor.submit(_fetch_and_evaluate, row)
            futures[f] = row["code"]
            import time
            time.sleep(settings.scan_submit_interval)

        for future in as_completed(futures):
            try:
                result = future.result()
                if result == "error":
                    errors += 1
                elif result is not None:
                    results.append(result)
            except Exception:
                errors += 1

    return results, errors

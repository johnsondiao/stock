"""选股服务 - 同步按需执行（前台触发, 只读缓存）

架构约定:
- 数据新鲜度由后台数据更新服务 (data_updater) 保证
- 选股在前台按需执行: POST /api/screen 同步跑完直接返回结果
- 不再使用后台线程 + 轮询
"""

import json
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from app.config import settings
from app.data.provider import get_provider
from app.data import cache
from app.strategy.base import Signal
from app.strategy import registry as strategy_registry
from app.log_config import get_logger

logger = get_logger(__name__)


def run_screen(strategy_name: str, params: dict,
               prefilter: dict | None = None) -> dict:
    """
    同步执行选股并返回完整结果

    :param strategy_name: 策略名称
    :param params: 策略参数
    :param prefilter: 预筛条件 {min_price, max_price, exclude_st}
    :return: {task_id, total_scanned, matched_count, results, ...}
    """
    strategy = strategy_registry.get(strategy_name)
    if strategy is None:
        raise ValueError(f"未知策略: {strategy_name}")

    task_id = uuid.uuid4().hex[:12]
    provider = get_provider()
    logger.info("[%s] 选股开始: strategy=%s params=%s", task_id, strategy_name, params)

    # Step 1: 行情快照（缓存新鲜则直接用, 由后台更新服务保持新鲜）
    snapshot = provider.get_all_stocks()
    if snapshot.empty:
        raise RuntimeError("行情快照为空, 请检查数据服务")
    logger.info("[%s] 行情快照: %d 只股票", task_id, len(snapshot))

    # Step 2: 预筛选
    candidates = _apply_prefilter(snapshot, prefilter or {})
    logger.info("[%s] 预筛选后: %d 只候选 (排除 %d 只)",
                task_id, len(candidates), len(snapshot) - len(candidates))

    # Step 3: 评估
    # 组合策略走向量化快速通道（2次SQL+矩阵计算, 秒级）;
    # 过闸门但缺5分钟缓存的股票回退逐股按需拉取（限流器兜底）
    total = len(candidates)
    results: list[dict] = []
    errors = 0
    processed = total

    if strategy.name == "ma_combo":
        from app.service.fast_combo import evaluate_combo_fast
        fast = evaluate_combo_fast(params, candidates)
    else:
        fast = None

    if fast is not None:
        results = fast["results"]
        pending = fast["pending_codes"]
        logger.info("[%s] 快速通道: 命中 %d 只, 待补数据 %d 只",
                    task_id, len(results), len(pending))
        if pending:
            sub = candidates[candidates["code"].isin(pending)].reset_index(drop=True)
            batch_results, batch_errors = _process_batch(sub, strategy, params, provider)
            results.extend(batch_results)
            errors += batch_errors
    else:
        # 通用逐股模式（其他策略或快速通道不可用）
        cached_hourly = cache.get_cached_codes("hourly_kline")
        processed = 0
        batch_size = settings.scan_batch_size
        for batch_start in range(0, total, batch_size):
            batch = candidates.iloc[batch_start:batch_start + batch_size]
            batch_results, batch_errors = _process_batch(batch, strategy, params, provider)
            results.extend(batch_results)
            errors += batch_errors
            processed += len(batch)

            logger.info("[%s] 进度: %d/%d, 匹配: %d, 错误: %d",
                        task_id, processed, total, len(results), errors)

            # 仅当批次中有股票需要拉API时才限流等待（纯缓存批次直接继续）
            api_needed = sum(1 for c in batch["code"] if c not in cached_hourly)
            if api_needed > 0 and batch_start + batch_size < total:
                import time
                time.sleep(settings.scan_batch_pause)

    # Step 4: 排序 + 保存结果（供历史查询）
    results.sort(key=lambda x: x.get("score", 0), reverse=True)

    from datetime import datetime
    result_data = {
        "task_id": task_id,
        "strategy": strategy_name,
        "params": params,
        "total_scanned": total,
        "matched_count": len(results),
        "errors": errors,
        "results": results,
        "completed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    cache.save_screen_task(
        task_id, strategy_name, params,
        status="completed", progress=total, total=total,
        matched=len(results), errors=errors,
        result_json=json.dumps(result_data, ensure_ascii=False, default=str),
    )
    logger.info("[%s] 选股完成: 扫描 %d 只, 匹配 %d 只, 错误 %d",
                task_id, total, len(results), errors)
    return result_data


def get_task_result(task_id: str) -> dict | None:
    """获取历史选股结果"""
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


def _apply_prefilter(df: pd.DataFrame, prefilter: dict) -> pd.DataFrame:
    """
    应用预筛选条件
    注意: 非交易时间 volume 可能为 0，不应排除
    """
    mask = pd.Series(True, index=df.index)

    # 排除 ST 和退市股
    if prefilter.get("exclude_st", True):
        if "name" in df.columns:
            mask &= ~df["name"].str.contains("ST|退", case=False, na=False)

    # 价格区间
    min_price = prefilter.get("min_price")
    if min_price:
        mask &= df["price"] >= min_price
    max_price = prefilter.get("max_price")
    if max_price:
        mask &= df["price"] <= max_price

    # 排除停牌: 只在交易时间过滤（有成交量数据时）
    if "volume" in df.columns:
        has_volume = (df["volume"] > 0).sum()
        if has_volume > len(df) * 0.1:  # 超过10%有成交量说明是交易时间
            mask &= df["volume"] > 0

    return df[mask].reset_index(drop=True)


def _process_batch(batch: pd.DataFrame, strategy, params: dict, provider) -> tuple:
    """处理一批候选股票（并发读缓存 + 评估策略）"""
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

            if strategy.dual_timeframe:
                # 双周期策略: 先过 60分钟+日线闸门，通过后才取 5 分钟数据（省请求）
                kline_daily = provider.get_daily_kline(code)
                gate = strategy.evaluate_gate(kline, params, kline_daily=kline_daily)
                if not gate.get("passed", False):
                    return None
                need_5min = params.get("min_slow", 144) + params.get("min_lookback", 48) + 10
                kline_5min = provider.get_5min_kline(code, min_candles=need_5min)
                if kline_5min.empty:
                    return None
                eval_result = strategy.evaluate_entry(kline_5min, gate, params)
            else:
                eval_result = strategy.evaluate(kline, params)

            signal = eval_result.get("signal", Signal.NEUTRAL)
            score = eval_result.get("score", 0)
            details = eval_result.get("details", {})

            # 只保留有意义的信号
            if strategy.dual_timeframe:
                if score < 55:
                    return None
            elif details.get("above_count", 0) < params.get("min_above", 4) and score < 50:
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

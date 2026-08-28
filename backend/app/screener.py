"""选股引擎 - 基于技术指标的多条件组合筛选"""

import pandas as pd
import numpy as np
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.data_client import get_realtime_quotes, get_stock_history, get_hourly_history, get_hourly_history_cached, load_cached_hourly, save_hourly_cache, get_cache_stats
from app.indicators import calc_all_indicators, calc_ma_strategy, check_ma_open_signal, MA_STRATEGY_PERIODS


# ── 筛选条件定义 ──────────────────────────────────────────

class ScreenCondition:
    """单个筛选条件"""
    def __init__(self, field: str, operator: str, value: float):
        self.field = field        # 指标字段名
        self.operator = operator  # gt / lt / eq / between
        self.value = value        # 阈值
        self.value2 = None        # between 时的第二个值

    def to_dict(self) -> dict:
        d = {"field": self.field, "operator": self.operator, "value": self.value}
        if self.value2 is not None:
            d["value2"] = self.value2
        return d


# ── 预筛选（实时行情快速过滤） ────────────────────────────

def pre_filter(df: pd.DataFrame,
               min_price: float = 0,
               max_price: float = 99999,
               min_volume: float = 0,
               min_market_cap: float = 0,
               exclude_st: bool = True,
               exclude_new: bool = True) -> pd.DataFrame:
    """基于实时行情的快速预筛选，减少后续指标计算量"""
    result = df.copy()

    # 价格区间
    result = result[(result["price"] >= min_price) & (result["price"] <= max_price)]

    # 最小成交量
    if min_volume > 0:
        result = result[result["volume"] >= min_volume]

    # 最小市值
    if min_market_cap > 0:
        result = result[result["total_mv"] >= min_market_cap * 1e8]

    # 排除 ST
    if exclude_st:
        result = result[~result["name"].str.contains("ST", case=False, na=False)]

    return result


# ── 技术面筛选 ────────────────────────────────────────────

def _check_condition(row: pd.Series, field: str, operator: str, value: float, value2: float = None) -> bool:
    """检查单条条件是否满足"""
    val = row.get(field)
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return False
    if operator == "gt":
        return val > value
    elif operator == "lt":
        return val < value
    elif operator == "gte":
        return val >= value
    elif operator == "lte":
        return val <= value
    elif operator == "eq":
        return abs(val - value) < 1e-6
    elif operator == "between":
        return value <= val <= (value2 or value)
    return False


def screen_by_indicators(candidates: pd.DataFrame,
                         conditions: list[dict],
                         lookback_days: int = 120) -> list[dict]:
    """
    对候选股票逐一计算技术指标并筛选
    :param candidates: 预筛选后的 DataFrame（需含 code, name 列）
    :param conditions: 筛选条件列表 [{"field": "macd", "operator": "gt", "value": 0}, ...]
    :param lookback_days: 回看天数（用于计算指标）
    :return: 符合条件的股票列表
    """
    from datetime import datetime, timedelta
    start = (datetime.now() - timedelta(days=lookback_days * 2)).strftime("%Y%m%d")
    results = []

    for _, row in candidates.iterrows():
        code = row["code"]
        try:
            hist = get_stock_history(code, start_date=start)
            if len(hist) < 60:
                continue
            hist = calc_all_indicators(hist)
            latest = hist.iloc[-1]

            passed = True
            indicator_values = {}
            for cond in conditions:
                field = cond["field"]
                op = cond["operator"]
                val = cond["value"]
                val2 = cond.get("value2")
                if not _check_condition(latest, field, op, val, val2):
                    passed = False
                    break
                indicator_values[field] = latest.get(field)

            if passed:
                results.append({
                    "code": code,
                    "name": row["name"],
                    "price": float(row.get("price", 0)),
                    "pct_change": float(row.get("pct_change", 0)),
                    "volume": float(row.get("volume", 0)),
                    "indicators": {k: round(float(v), 4) if not np.isnan(v) else None
                                   for k, v in indicator_values.items()},
                    # 附带关键指标供前端展示
                    "macd_dif": round(float(latest.get("dif", 0)), 4),
                    "macd_dea": round(float(latest.get("dea", 0)), 4),
                    "rsi": round(float(latest.get("rsi14", 0)), 2),
                    "k": round(float(latest.get("k", 0)), 2),
                    "d": round(float(latest.get("d", 0)), 2),
                    "j": round(float(latest.get("j", 0)), 2),
                    "ma5": round(float(latest.get("ma5", 0)), 2),
                    "ma20": round(float(latest.get("ma20", 0)), 2),
                })
        except Exception as e:
            continue

    return results


def prefilter_with_cache(candidates: pd.DataFrame, max_deviation: float = 0.10) -> tuple:
    """
    利用缓存的均线数据快速预筛，排除明显不符合的股票
    :param candidates: 候选股票 DataFrame (含 code, price 列)
    :param max_deviation: 价格低于 MA169 超过此比例则排除
    :return: (通过预筛的候选, 被排除的数量)
    """
    passed = []
    skipped = 0
    for _, row in candidates.iterrows():
        code = row["code"]
        price = float(row.get("price", 0))
        cached = load_cached_hourly(code)
        if cached.empty or len(cached) < 169:
            # 无缓存或数据不足，保留候选（需要全量获取）
            passed.append(row)
            continue
        # 用缓存计算 MA169
        ma169 = cached['close'].tail(169).mean()
        if price < ma169 * (1 - max_deviation):
            # 价格远低于 MA169，不可能站上全部 4 条均线
            skipped += 1
        else:
            passed.append(row)
    result_df = pd.DataFrame(passed) if passed else pd.DataFrame()
    return result_df, skipped


# ── MA 均线多头策略选股 ──────────────────────────────────

def _fetch_one_hourly(code: str, start: str):
    """获取单只股票的小时K线（供并发调用，带缓存）"""
    import time as _t
    for attempt in range(3):
        try:
            hist = get_hourly_history_cached(code, period="60", start_date=start)
            return code, hist, None
        except Exception as e:
            is_rate_limited = '456' in str(e) or 'Client Error' in str(e)
            if is_rate_limited:
                backoff = min(15 * (2 ** attempt), 180)
                _t.sleep(backoff)
            elif attempt < 2:
                _t.sleep(2)
            else:
                return code, None, str(e)
    return code, None, "max_retries"


def screen_ma_strategy(candidates: pd.DataFrame,
                       min_above: int = 4) -> list[dict]:
    """
    MA 均线多头策略选股（1小时K线）- 并发加速版
    均线参数: MA12, MA60, MA144, MA169
    """
    import time
    import random
    from datetime import datetime, timedelta

    start = (datetime.now() - timedelta(days=100)).strftime("%Y%m%d")
    total = len(candidates)

    # ── 并发参数 ──
    max_workers = 3          # 并发线程数
    submit_interval = 0.15   # 提交任务间隔(秒)，控制请求速率
    batch_size = 60          # 每批数量
    batch_pause = 10         # 每批后暂停秒数

    print(f"   🚀 并发模式: {max_workers} 线程, 共 {total} 只股票")

    # 构建任务列表
    tasks = []
    for _, row in candidates.iterrows():
        tasks.append((row["code"], row["name"],
                      float(row.get("price", 0)),
                      float(row.get("pct_change", 0)),
                      float(row.get("volume", 0))))

    results = []
    processed = 0
    error_count = 0
    skip_count = 0
    t0 = time.time()

    # 分批并发处理
    for batch_start in range(0, len(tasks), batch_size):
        batch = tasks[batch_start:batch_start + batch_size]

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for i, (code, name, price, pct, vol) in enumerate(batch):
                f = executor.submit(_fetch_one_hourly, code, start)
                futures[f] = (code, name, price, pct, vol)
                time.sleep(submit_interval)

            for future in as_completed(futures):
                processed += 1
                code, name, price, pct, vol = futures[future]
                code_r, hist, err = future.result()

                if hist is None or len(hist) < 170:
                    skip_count += 1
                    if err and error_count < 10:
                        print(f"  [{processed}/{total}] ❌ {code} {err}")
                        error_count += 1
                else:
                    try:
                        signal = check_ma_open_signal(hist)
                        if signal["above_count"] >= min_above:
                            hist_with_ma = calc_ma_strategy(hist)
                            latest = hist_with_ma.iloc[-1]
                            fresh = signal['fresh_candles']
                            fresh_tag = f"刚站上{fresh}根" if fresh <= 4 else f"已站上{fresh}根"
                            results.append({
                                "code": code,
                                "name": name,
                                "price": price,
                                "pct_change": pct,
                                "volume": vol,
                                "above_count": signal["above_count"],
                                "total_ma": signal["total_ma"],
                                "open_signal": signal["open_signal"],
                                "ma_aligned": signal["ma_aligned"],
                                "fresh_candles": fresh,
                                "ma12": round(float(latest.get("ma12", 0)), 2),
                                "ma60": round(float(latest.get("ma60", 0)), 2),
                                "ma144": round(float(latest.get("ma144", 0)), 2),
                                "ma169": round(float(latest.get("ma169", 0)), 2),
                                "ma_details": signal["ma_details"],
                            })
                            print(f"  [{processed}/{total}] ✅ {code} {name} 站上{signal['above_count']}条均线 ({fresh_tag})")
                    except Exception as e:
                        error_count += 1

        elapsed = time.time() - t0
        speed = processed / elapsed if elapsed > 0 else 0
        eta = (total - processed) / speed / 60 if speed > 0 else 0
        abs_idx = batch_start + len(batch)
        print(f"  [{abs_idx}/{total}] 匹配:{len(results)} 跳过:{skip_count} 错误:{error_count} | {speed:.1f}只/分 ETA:{eta:.0f}分")

        # 批次间暂停，让 API 限流恢复
        if abs_idx < total:
            time.sleep(batch_pause)

    elapsed_total = time.time() - t0
    print(f"\n📊 统计: 共{total}只, 匹配{len(results)}只, 跳过{skip_count}只, 错误{error_count}只")
    print(f"⏱️ 耗时: {elapsed_total/60:.1f} 分钟 (平均 {total/elapsed_total*60:.0f}只/分)")

    # 排序: 站上均线数降序 > 刚站上的优先(fresh_candles升序) > 多头排列优先
    results.sort(key=lambda x: (x["above_count"], -x["fresh_candles"], x["ma_aligned"]), reverse=True)
    return results

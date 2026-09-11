"""板块成色评估 - 基于"板块内齐涨"实证结论过滤选股结果

实证依据 (2025-01~2026-09, 1627 个观测, 样本外验证, 详见
用户级 skill a-share-sector-mainline / 项目根 sector_mainline.py):
- 板块内个股 5 日涨幅标准差(离散度)最小的 30% 组: 真主线率 43.1%,
  未来 20 日超额 +1.51%
- 离散度最大的 30% 组(靠龙头拉抬): 真主线率 18.0%, 超额 -1.77%
=> "买个股先看板块: 板块在涨 且 板块内涨得齐" 才是加分项

本模块职责:
1. compute_sector_stats(): 从 daily_kline 计算各板块离散度/中位涨幅/上涨占比
2. annotate_and_filter(): 给选股命中结果打板块成色标签, 并按规则过滤
   (被过滤的保留在 sector_filtered_out, 附原因, 透明可查)

规则(可通过 params 覆盖):
- sector_filter:      是否启用过滤, 默认 True
- sector_disp_pct:    离散度须排进最齐的前 N 比例, 默认 0.30
- sector_require_rising: 板块 5 日中位涨幅须 > 0, 默认 True
"""

import threading

import numpy as np
import pandas as pd

from app.config import settings
from app.database import get_db
from app.log_config import get_logger

logger = get_logger(__name__)

DEFAULT_DISP_PCT = 0.30
MIN_SECTOR_MEMBERS = 5
MIN_FULL_COVERAGE = 2000      # 当日日线覆盖低于此数视为不完整, 不用
LOOKBACK_DAYS = 5             # 计算 5 日涨幅

# ── 行业映射缓存 ──────────────────────────────────────────
_map_lock = threading.Lock()
_map_cache: dict | None = None
_map_mtime: float | None = None


def load_industry_map() -> dict[str, str]:
    """code -> sector 映射, 带文件 mtime 缓存; 文件缺失返回空 dict"""
    global _map_cache, _map_mtime
    path = settings.industry_map_path
    if not path.exists():
        logger.warning("行业映射文件不存在: %s", path)
        return {}
    mtime = path.stat().st_mtime
    with _map_lock:
        if _map_cache is not None and mtime == _map_mtime:
            return _map_cache
        df = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
        _map_cache = dict(zip(df["code"], df["sector"]))
        _map_mtime = mtime
        logger.info("行业映射已加载: %d 只, %d 个行业",
                    len(_map_cache), df["sector"].nunique())
        return _map_cache


# ── 板块统计(纯函数, 便于测试) ────────────────────────────

def stats_from_close(px: pd.DataFrame, imap: dict[str, str],
                     lookback: int = LOOKBACK_DAYS) -> pd.DataFrame:
    """
    :param px: index=日期(YYYY-MM-DD), columns=code, values=close
    :param imap: code -> sector
    :return: DataFrame(index=sector): disp / ret5 / breadth / n / disp_rank
             disp_rank 为离散度百分位(0=最齐, 1=最散)
    """
    if px.empty or len(px) < lookback + 1:
        return pd.DataFrame()
    # 只保留最近 lookback+1 个交易日
    px = px.tail(lookback + 1)
    ret = (px.iloc[-1] / px.iloc[0] - 1) * 100      # 每股 lookback 日涨幅%

    rows = []
    for code, sector in imap.items():
        if code in ret.index:
            rows.append((code, sector))
    if not rows:
        return pd.DataFrame()
    members = pd.DataFrame(rows, columns=["code", "sector"])

    stats = []
    for sector, grp in members.groupby("sector"):
        r = ret.loc[grp["code"]].dropna()
        if len(r) < MIN_SECTOR_MEMBERS:
            continue
        stats.append({
            "sector": sector,
            "disp": float(r.std()),          # 离散度: 越小越齐
            "ret5": float(r.median()),       # 板块中位涨幅
            "breadth": float((r > 0).mean() * 100),  # 上涨占比%
            "n": int(len(r)),
        })
    if not stats:
        return pd.DataFrame()
    out = pd.DataFrame(stats).set_index("sector")
    # 离散度百分位排名(min-max归一化): 0=最齐, 1=最散
    # (rank(pct=True) 在板块数很少时分辨率为 1/n, 会误伤最齐的板块)
    r = out["disp"].rank(method="average")
    n = len(out)
    out["disp_rank"] = (r - 1) / (n - 1) if n > 1 else 1.0
    return out


# ── 从数据库取收盘价并计算 ────────────────────────────────

def compute_sector_stats() -> pd.DataFrame | None:
    """读取最近日线计算板块统计; 数据不足返回 None"""
    with get_db() as conn:
        df = pd.read_sql_query(
            "SELECT substr(date,1,10) AS d, code, close FROM daily_kline "
            "WHERE date >= date('now', '-20 day')",
            conn,
        )
    if df.empty:
        return None
    # 只取覆盖完整的交易日(排除盘中渐进写入的当日)
    cov = df.groupby("d")["code"].nunique()
    full_days = cov[cov >= MIN_FULL_COVERAGE].index
    if len(full_days) < LOOKBACK_DAYS + 1:
        logger.warning("板块统计: 完整交易日不足 (%d), 跳过", len(full_days))
        return None
    # 排除当日(可能盘中渐进写入, 覆盖虽足但价格未定) —— 用倒数第二完整日之前
    full_days = full_days.sort_values()
    use_days = full_days[:-1] if len(full_days) > 1 else full_days
    df = df[df["d"].isin(use_days)]
    px = df.pivot_table(index="d", columns="code",
                        values="close", aggfunc="last").sort_index()
    return stats_from_close(px, load_industry_map())


# ── 标注 + 过滤 ──────────────────────────────────────────

def annotate_and_filter(results: list[dict], params: dict | None = None,
                        stats: pd.DataFrame | None = None,
                        imap: dict[str, str] | None = None
                        ) -> tuple[list[dict], list[dict]]:
    """
    给命中结果附加板块成色字段并按规则过滤。

    :param imap: code -> sector 映射, 缺省时自动加载(测试可注入)
    :return: (保留的结果, 被过滤的结果[含原因字段 sector_reason])
    """
    if not results:
        return results, []
    p = params or {}
    enabled = p.get("sector_filter", True)
    disp_pct = float(p.get("sector_disp_pct", DEFAULT_DISP_PCT))
    require_rising = p.get("sector_require_rising", True)

    if not enabled:
        return results, []

    if stats is None:
        stats = compute_sector_stats()
    if stats is None or stats.empty:
        logger.warning("板块成色: 统计不可用, 本次不过滤")
        return results, []

    if imap is None:
        imap = load_industry_map()

    kept, dropped = [], []
    for item in results:
        code = str(item.get("code", ""))
        sector = imap.get(code)
        item["sector"] = sector or "未知"
        if sector is None or sector not in stats.index:
            # 行业映射缺失: 不因数据缺口误杀, 但明确标注
            item["sector_reason"] = "行业映射缺失"
            kept.append(item)
            continue
        s = stats.loc[sector]
        item["sector_disp"] = round(float(s["disp"]), 2)
        item["sector_ret5"] = round(float(s["ret5"]), 2)
        item["sector_breadth"] = round(float(s["breadth"]))
        item["sector_rank"] = f"{int((stats['disp'] < s['disp']).sum()) + 1}/{len(stats)}"

        uniform = float(s["disp_rank"]) <= disp_pct
        rising = (not require_rising) or float(s["ret5"]) > 0
        if uniform and rising:
            item["sector_reason"] = "板块齐涨"
            kept.append(item)
        else:
            reasons = []
            if not rising:
                reasons.append(f"板块5日中位{s['ret5']:+.1f}%未涨")
            if not uniform:
                reasons.append(f"离散{s['disp']:.1f}偏散(需排前{int(disp_pct*100)}%齐)")
            item["sector_reason"] = ";".join(reasons)
            dropped.append(item)
    logger.info("板块成色过滤: 保留 %d, 过滤 %d", len(kept), len(dropped))
    return kept, dropped

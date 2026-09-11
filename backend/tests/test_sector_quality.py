"""板块成色过滤 (sector_quality) 回归测试 - 纯函数部分"""

import pandas as pd

from app.strategy.sector_quality import stats_from_close, annotate_and_filter


def _px():
    """6个交易日: 电力行业5只齐涨, 酒店旅游5只靠龙头拉"""
    dates = [f"2026-09-{d:02d}" for d in range(1, 7)]
    data = {}
    for i in range(1, 6):                                  # 电力: 全部每天+1%
        data[f"6001{i:02d}"] = [100 * (1.01 ** t) for t in range(6)]
    data["600201"] = [100, 100, 100, 100, 100, 130]        # 龙头 +30%
    for i in (2, 3, 4, 5):                                 # 其余不动
        data[f"6002{i:02d}"] = [100, 100, 100, 100, 100, 100 + i - 5]
    return pd.DataFrame(data, index=dates)                 # index=日期, columns=code


def _imap():
    m = {f"6001{i:02d}": "电力行业" for i in range(1, 6)}
    m.update({f"6002{i:02d}": "酒店旅游" for i in range(1, 6)})
    return m


def test_stats_uniform_vs_leader_driven():
    """齐涨板块离散度应显著小于龙头拉抬板块"""
    stats = stats_from_close(_px(), _imap())
    assert "电力行业" in stats.index and "酒店旅游" in stats.index
    assert stats.loc["电力行业", "disp"] < stats.loc["酒店旅游", "disp"]
    assert stats.loc["电力行业", "disp"] < 1.0
    assert stats.loc["酒店旅游", "disp"] > 10.0
    # 酒店旅游中位涨幅<=0.25%: 龙头拉抬组中位数几乎不涨
    assert stats.loc["酒店旅游", "ret5"] < stats.loc["电力行业", "ret5"]
    assert stats.loc["酒店旅游", "disp_rank"] > stats.loc["电力行业", "disp_rank"]


def test_filter_keeps_uniform_rising_sector():
    """齐涨板块的股票保留, 龙头拉抬板块的股票被过滤且带原因"""
    stats = stats_from_close(_px(), _imap())
    results = [
        {"code": "600101", "name": "电力A", "score": 98},
        {"code": "600201", "name": "酒店A", "score": 98},
    ]
    kept, dropped = annotate_and_filter(results, params={}, stats=stats,
                                        imap=_imap())
    assert [r["code"] for r in kept] == ["600101"]
    assert [r["code"] for r in dropped] == ["600201"]
    assert kept[0]["sector"] == "电力行业"
    assert kept[0]["sector_reason"] == "板块齐涨"
    assert "板块5日中位" in dropped[0]["sector_reason"]
    assert dropped[0]["sector"] == "酒店旅游"
    assert "sector_disp" in dropped[0] and "sector_rank" in dropped[0]


def test_filter_disabled_keeps_all():
    stats = stats_from_close(_px(), _imap())
    results = [{"code": "600201", "name": "酒店A", "score": 98}]
    kept, dropped = annotate_and_filter(results, params={"sector_filter": False},
                                        stats=stats, imap=_imap())
    assert len(kept) == 1 and not dropped


def test_unknown_sector_not_killed():
    """行业映射缺失的股票不应被误杀"""
    stats = stats_from_close(_px(), _imap())
    results = [{"code": "999999", "name": "新股", "score": 98}]
    kept, dropped = annotate_and_filter(results, params={}, stats=stats,
                                        imap=_imap())
    assert len(kept) == 1 and kept[0]["sector"] == "未知"
    assert kept[0]["sector_reason"] == "行业映射缺失"
    assert not dropped


def test_falling_sector_filtered():
    """板块中位涨幅<=0 时即使齐也过滤(require_rising)"""
    dates = [f"2026-09-{d:02d}" for d in range(1, 7)]
    data = {f"7001{i:02d}": [100 * (0.99 ** t) for t in range(6)]
            for i in range(1, 6)}      # 5只齐跌
    px = pd.DataFrame(data, index=dates)
    imap = {f"7001{i:02d}": "煤炭行业" for i in range(1, 6)}
    stats = stats_from_close(px, imap)
    results = [{"code": "700101", "name": "煤炭A", "score": 98}]
    kept, dropped = annotate_and_filter(results, params={}, stats=stats, imap=imap)
    assert len(kept) == 0 and len(dropped) == 1
    assert "未涨" in dropped[0]["sector_reason"]


def test_disp_pct_override():
    """离散度百分位阈值可放宽"""
    dates = [f"2026-09-{d:02d}" for d in range(1, 7)]
    data = {}
    for i in range(1, 4):
        data[f"8001{i:02d}"] = [100 * (1.05 ** t) for t in range(6)]   # 3只+5%/天
    for i in range(4, 7):
        data[f"8001{i:02d}"] = [100 * (1.01 ** t) for t in range(6)]   # 3只+1%/天
    px = pd.DataFrame(data, index=dates)
    imap = {c: "机械行业" for c in data}
    stats = stats_from_close(px, imap)
    results = [{"code": "800101", "name": "机械A", "score": 98}]
    # 该板块是全库唯一板块 → disp_rank=1.0 > 0.30 → 默认过滤
    kept, _ = annotate_and_filter(results, params={}, stats=stats, imap=imap)
    assert len(kept) == 0
    # 放宽到 100% → 保留
    kept, _ = annotate_and_filter(
        results, params={"sector_disp_pct": 1.0}, stats=stats, imap=imap)
    assert len(kept) == 1

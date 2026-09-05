"""测试基本面预筛 (PE/价格/市值) 与估值合并"""

import pandas as pd
import pytest

from app.service import screener


def _snapshot():
    return pd.DataFrame({
        "code": ["600001", "600002", "600003", "600004", "600005"],
        "name": ["甲股份", "乙股份", "丙股份", "ST丁", "戊股份"],
        "price": [15.0, 25.0, 8.0, 5.0, 12.0],
        "pct_change": [1.0, 2.0, -1.0, 0.5, 3.0],
        "volume": [100.0] * 5,
        "pe": [50.0, 1200.0, 5.0, 30.0, 0.0],
        "pb": [2.0, 3.0, 1.0, 4.0, 0.0],
        "total_mv": [50e4, 200e4, 30e4, 10e4, 0.0],  # 万元
    })


class TestPrefilterPE:
    def test_pe_range(self, monkeypatch):
        # 估值数据已内嵌在快照里, 合并函数保持原样返回
        monkeypatch.setattr(screener.cache, "merge_fundamental", lambda df: df)
        out = screener._apply_prefilter(_snapshot(),
                                        {"pe_min": 10, "pe_max": 1000})
        # PE=1200 超上限; PE=5 低于下限; PE=0(亏损/无数据)排除; ST排除
        assert list(out["code"]) == ["600001"]

    def test_pe_max_excludes_loss(self, monkeypatch):
        """pe_max 条件隐含排除亏损股(PE<=0), 与东财'净利>0'等价"""
        monkeypatch.setattr(screener.cache, "merge_fundamental", lambda df: df)
        out = screener._apply_prefilter(_snapshot(), {"pe_max": 1000})
        assert "600005" not in out["code"].tolist()  # PE=0 被排除
        assert "600004" not in out["code"].tolist()  # ST 被排除

    def test_no_fund_condition_skips_merge(self, monkeypatch):
        called = []
        monkeypatch.setattr(screener.cache, "merge_fundamental",
                            lambda df: called.append(1) or df)
        out = screener._apply_prefilter(_snapshot(), {"max_price": 20})
        assert not called
        assert len(out) == 3  # 价格<=20 且非ST

    def test_price_and_pe_combined(self, monkeypatch):
        monkeypatch.setattr(screener.cache, "merge_fundamental", lambda df: df)
        out = screener._apply_prefilter(
            _snapshot(), {"max_price": 20, "pe_min": 10, "pe_max": 1000})
        assert list(out["code"]) == ["600001"]

    def test_mv_range(self, monkeypatch):
        monkeypatch.setattr(screener.cache, "merge_fundamental", lambda df: df)
        out = screener._apply_prefilter(_snapshot(), {"min_mv": 40})  # 40亿
        assert set(out["code"]) == {"600001", "600002"}


class TestMergeFundamental:
    def test_merge_fills_pe(self, monkeypatch):
        fund = pd.DataFrame({
            "code": ["600001", "600003"],
            "pe": [50.0, 5.0],
            "pb": [2.0, 1.0],
            "total_mv": [50e4, 30e4],
        })
        monkeypatch.setattr(screener.cache, "load_fundamental", lambda: fund)
        snap = _snapshot()
        snap["pe"] = 0.0  # 快照原始无估值
        snap["pb"] = 0.0
        snap["total_mv"] = 0.0
        merged = screener.cache.merge_fundamental(snap)
        row = merged[merged["code"] == "600001"].iloc[0]
        assert row["pe"] == 50.0
        assert row["total_mv"] == 50e4
        # 无估值数据的股票保持0
        row5 = merged[merged["code"] == "600005"].iloc[0]
        assert row5["pe"] == 0.0

    def test_merge_empty_fund(self, monkeypatch):
        monkeypatch.setattr(screener.cache, "load_fundamental",
                            lambda: pd.DataFrame())
        snap = _snapshot()
        merged = screener.cache.merge_fundamental(snap)
        assert len(merged) == len(snap)

"""测试 API 端点"""

import pytest
from fastapi.testclient import TestClient
from app.log_config import setup_logging
from app.database import init_db
from app.strategy.registry import auto_register
from app.api.main import create_app


@pytest.fixture(scope="module")
def client():
    setup_logging()
    init_db()
    auto_register()  # 测试环境需手动注册策略
    app = create_app()
    return TestClient(app)


class TestRootEndpoints:
    def test_root(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert "name" in data
        assert data["version"] == "2.0.0"

    def test_health(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestStrategyEndpoints:
    def test_list_strategies(self, client):
        resp = client.get("/api/strategy/list")
        assert resp.status_code == 200
        data = resp.json()
        assert "strategies" in data
        assert len(data["strategies"]) >= 1

    def test_get_strategy(self, client):
        resp = client.get("/api/strategy/ma_combo")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "ma_combo"
        assert "params_schema" in data

    def test_get_strategy_not_found(self, client):
        resp = client.get("/api/strategy/nonexistent")
        assert resp.status_code == 404

    def test_get_strategy_schema(self, client):
        resp = client.get("/api/strategy/ma_combo/schema")
        assert resp.status_code == 200
        data = resp.json()
        assert "params_schema" in data
        assert "hourly_fast" in data["params_schema"]


class TestMarketEndpoints:
    def test_snapshot_info(self, client):
        resp = client.get("/api/market/snapshot/info")
        assert resp.status_code == 200
        data = resp.json()
        assert "stocks_count" in data
        assert "is_fresh" in data


class TestScreenEndpoints:
    def test_start_screen_invalid_strategy(self, client):
        resp = client.post("/api/screen", json={
            "strategy": "nonexistent",
            "params": {},
        })
        assert resp.status_code == 400

    def test_start_screen_valid(self, client, monkeypatch):
        """选股同步执行: mock 掉真实扫描，验证接口返回完整结果"""
        from app.api.routes import screen as screen_route
        monkeypatch.setattr(
            screen_route.screener_service, "run_screen",
            lambda strategy_name, params, prefilter: {
                "task_id": "test123", "strategy": strategy_name,
                "total_scanned": 100, "matched_count": 0, "errors": 0,
                "results": [],
            },
        )
        resp = client.post("/api/screen", json={
            "strategy": "ma_combo",
            "params": {"min_above": 4},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "task_id" in data
        assert "results" in data
        assert data["strategy"] == "ma_combo"

    def test_get_task_result_not_found(self, client):
        resp = client.get("/api/screen/nonexistent/result")
        assert resp.status_code == 404

    def test_history(self, client):
        resp = client.get("/api/screen/history")
        assert resp.status_code == 200
        data = resp.json()
        assert "tasks" in data

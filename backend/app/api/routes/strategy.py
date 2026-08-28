"""策略相关 API 路由"""

from fastapi import APIRouter, HTTPException
from app.strategy import registry as strategy_registry

router = APIRouter(prefix="/strategy", tags=["策略"])


@router.get("/list")
def list_strategies():
    """获取所有可用策略列表"""
    return {"strategies": strategy_registry.list_all()}


@router.get("/{name}")
def get_strategy(name: str):
    """获取策略详情（含参数 schema）"""
    strategy = strategy_registry.get(name)
    if strategy is None:
        raise HTTPException(status_code=404, detail=f"策略不存在: {name}")
    return strategy.to_dict()


@router.get("/{name}/schema")
def get_strategy_schema(name: str):
    """获取策略参数 schema（供前端动态渲染表单）"""
    strategy = strategy_registry.get(name)
    if strategy is None:
        raise HTTPException(status_code=404, detail=f"策略不存在: {name}")
    return {"name": name, "params_schema": strategy.params_schema}

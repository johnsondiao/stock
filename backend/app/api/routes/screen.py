"""选股相关 API 路由（同步按需执行）"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.service import screener as screener_service

router = APIRouter(prefix="/screen", tags=["选股"])


class ScreenRequest(BaseModel):
    strategy: str
    params: dict = {}
    prefilter: dict | None = None


@router.post("")
def start_screen(req: ScreenRequest):
    """
    同步执行选股，直接返回完整结果
    数据由后台更新服务保持新鲜，选股只读缓存，通常几十秒内完成
    """
    try:
        return screener_service.run_screen(
            strategy_name=req.strategy,
            params=req.params,
            prefilter=req.prefilter,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
def screen_history(limit: int = 20):
    """获取历史选股任务列表"""
    tasks = screener_service.list_tasks(limit)
    return {"tasks": tasks}


@router.get("/{task_id}/result")
def get_task_result(task_id: str):
    """获取历史选股结果"""
    result = screener_service.get_task_result(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="结果不存在")
    return result

"""选股相关 API 路由"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.service import screener as screener_service

router = APIRouter(prefix="/screen", tags=["选股"])


class ScreenRequest(BaseModel):
    strategy: str
    params: dict = {}
    prefilter: dict | None = None


class TaskStatus(BaseModel):
    task_id: str
    status: str
    progress: int = 0
    total: int = 0
    matched: int = 0
    errors: int = 0


@router.post("")
def start_screen(req: ScreenRequest):
    """
    启动选股任务（立即返回 task_id）
    前端通过 GET /screen/{task_id} 轮询进度
    """
    try:
        task_id = screener_service.start_screen(
            strategy_name=req.strategy,
            params=req.params,
            prefilter=req.prefilter,
        )
        return {"task_id": task_id, "status": "pending"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
def screen_history(limit: int = 20):
    """获取历史选股任务列表"""
    tasks = screener_service.list_tasks(limit)
    return {"tasks": tasks}


@router.get("/{task_id}")
def get_task_status(task_id: str):
    """查询任务状态 + 进度"""
    status = screener_service.get_task_status(task_id)
    if status is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return status


@router.get("/{task_id}/result")
def get_task_result(task_id: str):
    """获取选股结果"""
    result = screener_service.get_task_result(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="结果不存在或任务未完成")
    return result

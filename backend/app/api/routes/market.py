"""行情相关 API 路由"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.service import market as market_service

router = APIRouter(prefix="/market", tags=["行情"])


class SnapshotInfo(BaseModel):
    stocks_count: int
    updated_at: str | None
    is_fresh: bool


class RefreshRequest(BaseModel):
    force: bool = False


@router.get("/snapshot/info", response_model=SnapshotInfo)
def snapshot_info():
    """获取行情快照状态信息"""
    return market_service.get_snapshot_info()


@router.get("/snapshot")
def get_snapshot():
    """获取最新行情快照（前100条预览）"""
    df = market_service.get_snapshot()
    if df.empty:
        return {"stocks": [], "total": 0}
    # 返回前100条预览
    records = df.head(100).to_dict(orient="records")
    return {"stocks": records, "total": len(df)}


@router.post("/refresh")
def refresh_snapshot(req: RefreshRequest):
    """手动刷新行情快照"""
    try:
        df = market_service.refresh_snapshot(force=req.force)
        return {"status": "ok", "stocks_count": len(df)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

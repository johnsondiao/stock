"""FastAPI 主入口 - A股技术指标选股系统"""

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import pandas as pd

from app.models import ScreenRequest, ScreenResponse, StockHistoryResponse, MAStrategyRequest
from app.data_client import get_realtime_quotes, get_stock_history
from app.screener import pre_filter, screen_by_indicators, screen_ma_strategy
from app.indicators import calc_all_indicators


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时预加载行情缓存"""
    print("🚀 A股选股系统启动中...")
    yield
    print("👋 系统关闭")


app = FastAPI(
    title="A股技术指标选股系统",
    version="0.1.0",
    lifespan=lifespan
)

# CORS - 允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── API 路由 ──────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/stocks")
async def list_stocks():
    """获取全部 A 股列表"""
    df = get_realtime_quotes()
    return {"total": len(df), "data": df[["code", "name", "price", "pct_change"]].to_dict("records")}


@app.post("/api/screen", response_model=ScreenResponse)
async def screen_stocks(req: ScreenRequest):
    """
    技术指标选股接口
    前端传入筛选条件，后端执行：
    1. 实时行情预筛选（价格/成交量/市值/ST）
    2. 逐只计算技术指标
    3. 按条件过滤返回结果
    """
    try:
        # 1. 获取实时行情
        quotes = get_realtime_quotes()

        # 2. 预筛选
        candidates = pre_filter(
            quotes,
            min_price=req.min_price,
            max_price=req.max_price,
            min_volume=req.min_volume,
            min_market_cap=req.min_market_cap,
            exclude_st=req.exclude_st,
        )

        # 3. 技术指标筛选
        conditions = [c.model_dump() for c in req.conditions]
        results = screen_by_indicators(candidates, conditions, req.lookback_days)

        return ScreenResponse(
            total=len(results),
            data=results,
            message=f"筛选完成，共 {len(results)} 只股票符合条件"
        )
    except Exception as e:
        return ScreenResponse(total=0, data=[], message=f"筛选出错: {str(e)}")


@app.get("/api/stock/{code}/history")
async def stock_history(code: str, days: int = Query(120, description="查看天数")):
    """获取个股历史行情 + 技术指标（供前端 K 线图使用）"""
    from datetime import datetime, timedelta
    start = (datetime.now() - timedelta(days=days * 2)).strftime("%Y%m%d")

    hist = get_stock_history(code, start_date=start)
    hist = calc_all_indicators(hist)
    hist = hist.tail(days)

    # 转 dict 列表，处理 NaN
    records = []
    for _, row in hist.iterrows():
        record = {}
        for col in hist.columns:
            val = row[col]
            if pd.isna(val):
                record[col] = None
            elif hasattr(val, "isoformat"):
                record[col] = val.strftime("%Y-%m-%d")
            else:
                record[col] = round(float(val), 4)
        records.append(record)

    return {"code": code, "data": records}


@app.post("/api/screen/ma", response_model=ScreenResponse)
async def screen_ma(req: MAStrategyRequest):
    """
    MA 均线多头策略选股接口（1小时K线）
    均线参数: MA12, MA60, MA144, MA169
    判断股价站上几条均线，全部站上则发出开仓信号
    """
    try:
        # 1. 获取实时行情
        quotes = get_realtime_quotes()

        # 2. 预筛选
        candidates = pre_filter(
            quotes,
            min_price=req.min_price,
            max_price=req.max_price,
            min_volume=req.min_volume,
            min_market_cap=req.min_market_cap,
            exclude_st=req.exclude_st,
        )

        # 3. MA 均线策略筛选
        results = screen_ma_strategy(candidates, min_above=req.min_above)

        return ScreenResponse(
            total=len(results),
            data=results,
            message=f"MA均线策略筛选完成，共 {len(results)} 只股票符合条件（站上≥{req.min_above}条均线）"
        )
    except Exception as e:
        return ScreenResponse(total=0, data=[], message=f"筛选出错: {str(e)}")


# ── 启动 ──────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

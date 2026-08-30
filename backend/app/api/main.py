"""FastAPI 应用入口 + 中间件"""

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.log_config import setup_logging, get_logger
from app.database import init_db, close_db
from app.strategy.registry import auto_register


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动
    setup_logging()
    logger = get_logger("app")
    logger.info("启动选股系统...")

    init_db()
    auto_register()

    # 启动后台数据更新服务（开盘时段自动保持数据新鲜）
    from app.service import data_updater
    data_updater.start()

    logger.info("系统就绪: http://%s:%s", settings.host, settings.port)
    yield

    # 关闭
    data_updater.stop()
    close_db()
    logger.info("系统已关闭")


def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    app = FastAPI(
        title="A 股选股系统",
        description="基于技术指标的 A 股自动选股系统",
        version="2.0.0",
        lifespan=lifespan,
    )

    # CORS 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 请求日志中间件
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration = round((time.time() - start) * 1000, 1)
        logger = get_logger("api")
        logger.info("%s %s -> %s (%.1fms)",
                    request.method, request.url.path, response.status_code, duration)
        return response

    # 注册路由
    from app.api.routes.market import router as market_router
    from app.api.routes.strategy import router as strategy_router
    from app.api.routes.screen import router as screen_router

    app.include_router(market_router, prefix="/api")
    app.include_router(strategy_router, prefix="/api")
    app.include_router(screen_router, prefix="/api")

    @app.get("/")
    def root():
        return {
            "name": "A 股选股系统",
            "version": "2.0.0",
            "docs": "/docs",
        }

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    return app


# 供 uvicorn 使用
app = create_app()

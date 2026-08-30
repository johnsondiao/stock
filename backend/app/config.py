"""全局配置管理 - 从环境变量/.env 读取，提供合理默认值"""

from pathlib import Path
from pydantic_settings import BaseSettings

# 项目根目录 (backend/)
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """应用配置，可通过环境变量或 .env 文件覆盖"""

    # ── 路径 ──
    data_dir: Path = BASE_DIR / "data"
    log_dir: Path = BASE_DIR / "logs"

    # ── 数据库 ──
    db_path: Path = BASE_DIR / "data" / "stock.db"

    # ── 扫描参数 ──
    scan_max_workers: int = 2          # 并发线程数（降低避免触发源站封禁）
    scan_batch_size: int = 50         # 每批处理数量
    scan_batch_pause: float = 10.0    # 批次间隔秒数
    scan_submit_interval: float = 0.3 # 并发任务提交间隔
    
    # ── 限流 ──
    rate_limit_per_minute: int = 30   # 每分钟最大 API 请求数（新浪 VIP 端点建议更保守）

    # ── 缓存 ──
    snapshot_ttl_seconds: int = 300    # 行情快照缓存有效期（5分钟）
    kline_max_candles: int = 300       # K线最大缓存根数（小时/日）
    kline_5min_max_candles: int = 600  # 5分钟K线最大缓存根数（满足 MA288 计算）
    kline_incremental_len: int = 30    # 增量更新拉取根数

    # ── 日志 ──
    log_level: str = "INFO"

    # ── 服务 ──
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = {"env_file": str(BASE_DIR / ".env"), "env_file_encoding": "utf-8"}


settings = Settings()

# 确保必要目录存在
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.log_dir.mkdir(parents=True, exist_ok=True)

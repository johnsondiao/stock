"""令牌桶限流器 - 控制全局 API 请求速率"""

import threading
import time
from app.log_config import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """
    令牌桶限流器
    以固定速率向桶中添加令牌，请求需获取令牌才能执行。
    桶满时多余令牌丢弃，桶空时请求阻塞等待。
    """

    def __init__(self, rate_per_minute: int = 60):
        """
        :param rate_per_minute: 每分钟允许的最大请求数
        """
        self._rate = rate_per_minute / 60.0  # 每秒生成令牌数
        self._tokens = float(rate_per_minute)  # 初始桶满
        self._max_tokens = float(rate_per_minute)
        self._last_time = time.monotonic()
        self._lock = threading.Lock()
        self._total_waits = 0
        self._total_wait_seconds = 0.0

    def acquire(self):
        """获取一个令牌，如果桶空则阻塞等待"""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_time
            self._last_time = now

            # 补充令牌
            self._tokens = min(self._max_tokens, self._tokens + elapsed * self._rate)

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return

        # 桶空，需要等待（在锁外等待以允许其他线程补充令牌）
        wait_time = (1.0 - self._tokens) / self._rate
        self._total_waits += 1
        self._total_wait_seconds += wait_time
        logger.debug("限流等待 %.2fs (累计等待 %d 次)", wait_time, self._total_waits)
        time.sleep(wait_time)

        # 等待后重新获取令牌
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_time
            self._last_time = now
            self._tokens = min(self._max_tokens, self._tokens + elapsed * self._rate)
            self._tokens = max(0.0, self._tokens - 1.0)

    def get_stats(self) -> dict:
        """获取限流器统计信息"""
        return {
            "rate_per_minute": int(self._rate * 60),
            "current_tokens": round(self._tokens, 2),
            "total_waits": self._total_waits,
            "total_wait_seconds": round(self._total_wait_seconds, 2),
        }


# 全局单例
_global_limiter: RateLimiter | None = None


def get_rate_limiter(rate_per_minute: int = 60) -> RateLimiter:
    """获取全局限流器实例"""
    global _global_limiter
    if _global_limiter is None:
        _global_limiter = RateLimiter(rate_per_minute)
    return _global_limiter

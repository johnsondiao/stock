"""测试令牌桶限流器"""

import time
import pytest
from app.data.rate_limiter import RateLimiter


class TestRateLimiter:
    def test_basic_acquire(self):
        limiter = RateLimiter(rate_per_minute=600)  # 很快，不会阻塞
        start = time.monotonic()
        for _ in range(10):
            limiter.acquire()
        elapsed = time.monotonic() - start
        # 600/min = 10/sec, 10次应该很快
        assert elapsed < 2.0

    def test_rate_limiting(self):
        limiter = RateLimiter(rate_per_minute=60)  # 1/sec
        start = time.monotonic()
        # 先消耗初始令牌
        for _ in range(5):
            limiter.acquire()
        elapsed = time.monotonic() - start
        # 初始桶满，前几个应该很快
        assert elapsed < 1.0

    def test_stats(self):
        limiter = RateLimiter(rate_per_minute=600)
        limiter.acquire()
        stats = limiter.get_stats()
        assert "total_waits" in stats
        assert "total_wait_seconds" in stats
        assert stats["total_waits"] >= 0

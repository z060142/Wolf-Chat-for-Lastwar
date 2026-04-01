"""
缓存管理器
提供带TTL的LRU缓存功能
"""
import time
import asyncio
from functools import wraps
from collections import OrderedDict
from typing import Any, Callable, Optional
import logging

logger = logging.getLogger(__name__)


class TTLCache:
    """带时间过期的LRU缓存"""

    def __init__(self, maxsize: int = 100, ttl: int = 300):
        """
        Args:
            maxsize: 最大缓存条目数
            ttl: 缓存有效期（秒），默认5分钟
        """
        self.maxsize = maxsize
        self.ttl = ttl
        self.cache = OrderedDict()
        self.timestamps = {}
        self._lock = asyncio.Lock()

    def _is_expired(self, key: str) -> bool:
        """检查缓存项是否过期"""
        if key not in self.timestamps:
            return True
        return time.time() - self.timestamps[key] > self.ttl

    async def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        async with self._lock:
            if key not in self.cache or self._is_expired(key):
                return None

            # LRU: 移到末尾
            self.cache.move_to_end(key)
            return self.cache[key]

    async def set(self, key: str, value: Any):
        """设置缓存值"""
        async with self._lock:
            # 如果已存在，先删除
            if key in self.cache:
                del self.cache[key]

            # 添加新值
            self.cache[key] = value
            self.timestamps[key] = time.time()

            # 如果超过maxsize，删除最旧的
            if len(self.cache) > self.maxsize:
                oldest_key = next(iter(self.cache))
                del self.cache[oldest_key]
                del self.timestamps[oldest_key]

    async def clear(self):
        """清空缓存"""
        async with self._lock:
            self.cache.clear()
            self.timestamps.clear()

    async def get_stats(self) -> dict:
        """获取缓存统计"""
        async with self._lock:
            valid_count = sum(1 for k in self.cache.keys() if not self._is_expired(k))
            return {
                "size": len(self.cache),
                "valid": valid_count,
                "expired": len(self.cache) - valid_count,
                "maxsize": self.maxsize,
                "ttl": self.ttl
            }


def cached(cache_instance: TTLCache, key_builder: Optional[Callable] = None):
    """
    缓存装饰器

    Args:
        cache_instance: TTLCache实例
        key_builder: 自定义key生成函数，接收函数参数，返回缓存key
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 生成缓存key
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                # 默认：函数名 + 参数
                cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"

            # 尝试从缓存获取
            cached_value = await cache_instance.get(cache_key)
            if cached_value is not None:
                logger.debug(f"缓存命中: {cache_key}")
                return cached_value

            # 执行函数
            logger.debug(f"缓存未命中，执行函数: {cache_key}")
            result = await func(*args, **kwargs)

            # 存入缓存
            await cache_instance.set(cache_key, result)

            return result

        return wrapper
    return decorator


# 全局缓存实例
profile_cache = TTLCache(maxsize=50, ttl=300)  # 50个用户profile，5分钟TTL
memory_cache = TTLCache(maxsize=100, ttl=180)  # 100条记忆，3分钟TTL

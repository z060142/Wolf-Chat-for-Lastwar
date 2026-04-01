"""
异步队列桥接
用于替代基于文件的IPC
"""
import asyncio
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)


class AsyncQueueBridge:
    """异步队列桥接器"""

    def __init__(self, name: str, maxsize: int = 0):
        """
        Args:
            name: 队列名称（用于日志）
            maxsize: 最大队列大小，0表示无限制
        """
        self.name = name
        self.queue = asyncio.Queue(maxsize=maxsize)

    async def put(self, item: Any, timeout: Optional[float] = None):
        """
        放入数据

        Args:
            item: 要放入的数据
            timeout: 超时时间（秒）
        """
        try:
            if timeout:
                await asyncio.wait_for(
                    self.queue.put(item),
                    timeout=timeout
                )
            else:
                await self.queue.put(item)

            logger.debug(f"队列 {self.name} 放入数据: {type(item).__name__}")
        except asyncio.TimeoutError:
            logger.error(f"队列 {self.name} 放入超时")
            raise

    async def get(self, timeout: Optional[float] = None) -> Any:
        """
        获取数据

        Args:
            timeout: 超时时间（秒）

        Returns:
            队列中的数据
        """
        try:
            if timeout:
                item = await asyncio.wait_for(
                    self.queue.get(),
                    timeout=timeout
                )
            else:
                item = await self.queue.get()

            logger.debug(f"队列 {self.name} 获取数据: {type(item).__name__}")
            return item
        except asyncio.TimeoutError:
            logger.error(f"队列 {self.name} 获取超时")
            raise

    def qsize(self) -> int:
        """返回当前队列大小"""
        return self.queue.qsize()

    def empty(self) -> bool:
        """队列是否为空"""
        return self.queue.empty()

    async def clear(self):
        """清空队列"""
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        logger.info(f"队列 {self.name} 已清空")

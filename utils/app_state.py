"""应用状态管理"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import asyncio


@dataclass
class AppState:
    """应用全局状态"""

    # 对话历史
    conversation_history: List[Dict] = field(default_factory=list)

    # 控制标志
    script_paused: bool = False
    shutdown_requested: bool = False

    # UI相关
    bubble_region: Optional[tuple] = None
    bubble_snapshot: Optional[Any] = None

    # 人格数据
    persona_details: Optional[Dict] = None

    # 锁
    _history_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def add_to_history(self, message: Dict):
        """线程安全地添加到历史"""
        async with self._history_lock:
            self.conversation_history.append(message)

    async def clear_history(self):
        """清空对话历史"""
        async with self._history_lock:
            self.conversation_history.clear()

    async def get_recent_history(self, count: int = 10) -> List[Dict]:
        """获取最近N条历史"""
        async with self._history_lock:
            return self.conversation_history[-count:]

    def pause(self):
        """暂停脚本"""
        self.script_paused = True

    def resume(self):
        """恢复脚本"""
        self.script_paused = False

    def request_shutdown(self):
        """请求关闭"""
        self.shutdown_requested = True

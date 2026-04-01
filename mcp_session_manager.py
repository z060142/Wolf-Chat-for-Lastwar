"""
MCP会话管理器
封装所有MCP服务器的启动、管理、清理逻辑
"""
import asyncio
import psutil
import signal
import os
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from contextlib import AsyncExitStack
import logging

logger = logging.getLogger(__name__)


@dataclass
class MCPServerInfo:
    """MCP服务器信息"""
    name: str
    config: dict
    session: Optional[ClientSession] = None
    process: Optional[any] = None
    pid: Optional[int] = None
    tools: List[dict] = field(default_factory=list)
    status: str = "stopped"  # stopped, starting, running, error


class MCPSessionManager:
    """MCP会话管理器"""

    def __init__(self, server_configs: Dict[str, dict]):
        """
        Args:
            server_configs: MCP服务器配置字典
        """
        self.server_configs = server_configs
        self.servers: Dict[str, MCPServerInfo] = {}
        self.exit_stack = AsyncExitStack()
        self._lock = asyncio.Lock()

    async def initialize_all(self):
        """并行初始化所有MCP服务器"""
        logger.info(f"开始初始化 {len(self.server_configs)} 个MCP服务器")

        # 创建服务器信息对象
        for name, config in self.server_configs.items():
            self.servers[name] = MCPServerInfo(name=name, config=config)

        # 并行启动所有服务器
        tasks = [
            self._initialize_server(name)
            for name in self.server_configs.keys()
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 统计结果
        success_count = sum(1 for r in results if r is True)
        logger.info(f"MCP服务器初始化完成: {success_count}/{len(results)} 成功")

        return success_count > 0

    async def _initialize_server(self, server_name: str, timeout: int = 30) -> bool:
        """
        初始化单个MCP服务器

        Args:
            server_name: 服务器名称
            timeout: 初始化超时时间（秒）

        Returns:
            是否成功
        """
        server = self.servers[server_name]
        server.status = "starting"

        try:
            config = server.config
            command = config.get("command")
            args = config.get("args", [])
            env = config.get("env", {})

            logger.info(f"启动MCP服务器: {server_name} ({command} {' '.join(args)})")

            # 准备环境变量
            process_env = os.environ.copy()
            process_env.update(env)

            # 创建服务器参数
            server_params = StdioServerParameters(
                command=command,
                args=args,
                env=process_env
            )

            # 启动服务器（带超时）
            stdio_transport = await asyncio.wait_for(
                stdio_client(server_params),
                timeout=timeout
            )

            read, write = await self.exit_stack.enter_async_context(stdio_transport)
            session = await self.exit_stack.enter_async_context(
                ClientSession(read, write)
            )

            # 初始化会话
            await session.initialize()

            # 保存session
            server.session = session
            server.status = "running"

            # 获取进程PID
            server.pid = await self._find_server_pid(server_name, command, args)

            # 发现工具
            tools = await self._discover_tools(session, timeout=10)
            server.tools = tools

            logger.info(
                f"MCP服务器 {server_name} 启动成功 "
                f"(PID: {server.pid}, 工具数: {len(tools)})"
            )

            return True

        except asyncio.TimeoutError:
            logger.error(f"MCP服务器 {server_name} 初始化超时")
            server.status = "error"
            return False
        except Exception as e:
            logger.error(f"MCP服务器 {server_name} 初始化失败: {e}")
            server.status = "error"
            return False

    async def _find_server_pid(self, server_name: str, command: str, args: List[str]) -> Optional[int]:
        """查找服务器进程PID"""
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = proc.info.get('cmdline') or []
                    cmdline_str = ' '.join(cmdline)

                    # Check if command is in the cmdline
                    if command in cmdline_str:
                        # Check if any of the args are in cmdline
                        if any(arg in cmdline_str for arg in args if arg):
                            return proc.info['pid']
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            return None
        except Exception as e:
            logger.warning(f"无法找到 {server_name} 的PID: {e}")
            return None

    async def _discover_tools(self, session: ClientSession, timeout: int = 30) -> List[dict]:
        """发现MCP服务器提供的工具"""
        try:
            import mcp_client
            tools = await asyncio.wait_for(
                mcp_client.list_mcp_tools(session),
                timeout=timeout
            )
            return tools
        except Exception as e:
            logger.error(f"工具发现失败: {e}")
            return []

    async def get_all_tools(self) -> List[dict]:
        """获取所有服务器的工具列表"""
        all_tools = []
        for server in self.servers.values():
            if server.status == "running":
                all_tools.extend(server.tools)
        return all_tools

    async def get_active_sessions(self) -> Dict[str, ClientSession]:
        """获取所有活跃的session"""
        return {
            name: server.session
            for name, server in self.servers.items()
            if server.session is not None and server.status == "running"
        }

    async def cleanup(self):
        """清理所有MCP资源"""
        logger.info("开始清理MCP资源...")

        # 1. 关闭AsyncExitStack（优雅关闭sessions）
        try:
            await asyncio.wait_for(self.exit_stack.aclose(), timeout=3.0)
            logger.info("MCP sessions已优雅关闭")
        except asyncio.TimeoutError:
            logger.warning("MCP sessions关闭超时")
        except Exception as e:
            logger.error(f"关闭MCP sessions时出错: {e}")

        # 2. 强制终止进程
        await self._force_kill_processes()

        logger.info("MCP资源清理完成")

    async def _force_kill_processes(self):
        """强制终止所有MCP进程"""
        for server in self.servers.values():
            if server.pid:
                try:
                    process = psutil.Process(server.pid)

                    # 先尝试优雅终止
                    process.terminate()

                    # 等待最多3秒
                    try:
                        process.wait(timeout=3)
                        logger.info(f"进程 {server.pid} ({server.name}) 已终止")
                    except psutil.TimeoutExpired:
                        # 强制杀死
                        process.kill()
                        logger.warning(f"进程 {server.pid} ({server.name}) 已强制杀死")

                except psutil.NoSuchProcess:
                    logger.debug(f"进程 {server.pid} 已不存在")
                except Exception as e:
                    logger.error(f"终止进程 {server.pid} 失败: {e}")

    def get_status_summary(self) -> dict:
        """获取所有服务器状态摘要"""
        summary = {}
        for name, server in self.servers.items():
            summary[name] = {
                "status": server.status,
                "pid": server.pid,
                "tool_count": len(server.tools)
            }
        return summary

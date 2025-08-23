#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Setup Threading Safe Wrappers
為 Setup.py 的現有進程管理邏輯提供線程安全包裝器
"""

import threading
import time
import subprocess
import logging
import os
from typing import Optional, Callable, Any, Dict, List
from .setup_state_manager import state_manager, ProcessType, ProcessState

logger = logging.getLogger(__name__)

class ThreadSafeProcessManager:
    """
    線程安全的進程管理器
    包裝現有的進程管理邏輯，添加線程安全保障
    """
    
    def __init__(self):
        self.state_manager = state_manager
        self._operation_lock = threading.RLock()
        
    def start_bot_process(self, command: list, cwd: str = None, **kwargs) -> bool:
        """線程安全的啟動 Bot 進程"""
        with self._operation_lock:
            try:
                # 檢查是否已有運行中的進程
                current_instance = self.state_manager.get_process_instance(ProcessType.BOT)
                if current_instance and self.state_manager.is_process_alive(ProcessType.BOT):
                    logger.warning("Bot process is already running")
                    return False
                
                # 設置狀態為啟動中
                self.state_manager.set_process_state(ProcessType.BOT, ProcessState.STARTING)
                
                # 啟動進程
                process = subprocess.Popen(
                    command,
                    cwd=cwd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    **kwargs
                )
                
                # 短暫等待確認進程啟動
                time.sleep(0.5)
                if process.poll() is None:
                    # 進程成功啟動
                    self.state_manager.set_process_instance(ProcessType.BOT, process)
                    self.state_manager.set_process_state(ProcessType.BOT, ProcessState.RUNNING, {
                        'pid': process.pid,
                        'command': command,
                        'start_time': time.time()
                    })
                    logger.info(f"Bot process started successfully with PID: {process.pid}")
                    return True
                else:
                    # 進程啟動失敗
                    self.state_manager.set_process_state(ProcessType.BOT, ProcessState.ERROR, {
                        'return_code': process.returncode,
                        'command': command,
                        'error_time': time.time()
                    })
                    logger.error(f"Bot process failed to start, return code: {process.returncode}")
                    return False
                    
            except Exception as e:
                self.state_manager.set_process_state(ProcessType.BOT, ProcessState.ERROR, {
                    'exception': str(e),
                    'command': command,
                    'error_time': time.time()
                })
                logger.error(f"Error starting bot process: {e}")
                return False
    
    def stop_bot_process(self, timeout: float = 10.0) -> bool:
        """線程安全的停止 Bot 進程"""
        with self._operation_lock:
            try:
                bot_instance = self.state_manager.get_process_instance(ProcessType.BOT)
                if not bot_instance:
                    logger.info("No bot process to stop")
                    self.state_manager.set_process_state(ProcessType.BOT, ProcessState.STOPPED)
                    return True
                
                # 設置狀態為停止中
                self.state_manager.set_process_state(ProcessType.BOT, ProcessState.STOPPING)
                
                # 嘗試優雅停止
                if self.state_manager.is_process_alive(ProcessType.BOT):
                    bot_instance.terminate()
                    
                    # 等待進程結束
                    try:
                        bot_instance.wait(timeout=timeout)
                        logger.info("Bot process terminated gracefully")
                    except subprocess.TimeoutExpired:
                        # 強制殺死進程
                        logger.warning("Bot process did not terminate gracefully, killing...")
                        bot_instance.kill()
                        bot_instance.wait(timeout=2.0)
                
                # 清理狀態
                self.state_manager.set_process_instance(ProcessType.BOT, None)
                self.state_manager.set_process_state(ProcessType.BOT, ProcessState.STOPPED, {
                    'stop_time': time.time()
                })
                
                return True
                
            except Exception as e:
                self.state_manager.set_process_state(ProcessType.BOT, ProcessState.ERROR, {
                    'exception': str(e),
                    'error_time': time.time()
                })
                logger.error(f"Error stopping bot process: {e}")
                return False
    
    def start_game_process(self, command: list, cwd: str = None, **kwargs) -> bool:
        """線程安全的啟動遊戲進程"""
        with self._operation_lock:
            try:
                # 檢查是否已有運行中的進程
                current_instance = self.state_manager.get_process_instance(ProcessType.GAME)
                if current_instance and self.state_manager.is_process_alive(ProcessType.GAME):
                    logger.warning("Game process is already running (managed instance)")
                    return True  # 改為返回True，因為目標已達成
                
                # 檢查系統中是否已有同名進程運行
                import psutil
                game_exe_name = command[0].split('\\')[-1] if '\\' in command[0] else command[0].split('/')[-1]
                try:
                    for proc in psutil.process_iter(['pid', 'name']):
                        if proc.info['name'] and proc.info['name'].lower() == game_exe_name.lower():
                            logger.info(f"Found existing game process: {game_exe_name} PID {proc.info['pid']}")
                            # 不將現有進程註冊到狀態管理器，因為我們無法控制它
                            return True  # 遊戲已在運行，視為成功
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
                
                # 設置狀態為啟動中
                self.state_manager.set_process_state(ProcessType.GAME, ProcessState.STARTING)
                
                # 啟動進程
                process = subprocess.Popen(
                    command,
                    cwd=cwd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    **kwargs
                )
                
                # 短暫等待確認進程啟動
                time.sleep(0.5)
                
                # 檢查進程狀態
                return_code = process.poll()
                
                if return_code is None:
                    # 進程仍在運行，這是直接啟動模式
                    self.state_manager.set_process_instance(ProcessType.GAME, process)
                    self.state_manager.set_process_state(ProcessType.GAME, ProcessState.RUNNING, {
                        'pid': process.pid,
                        'command': command,
                        'start_time': time.time()
                    })
                    logger.info(f"Game process started successfully (direct mode) with PID: {process.pid}")
                    return True
                    
                elif return_code == 0:
                    # 進程正常退出，可能是啟動器模式
                    logger.info(f"Game launcher exited normally (return code: 0), checking for game process in background...")
                    
                    # 優化的等待策略：快速檢查 + 逐漸減少頻率
                    max_wait_time = 8.0  # 最多等待8秒
                    
                    # 第一階段：快速檢查（前3秒，每0.5秒檢查一次）
                    quick_check_time = 3.0
                    quick_interval = 0.5
                    quick_checks = int(quick_check_time / quick_interval)
                    
                    logger.info("Game launcher mode: Phase 1 - Quick detection (0.5s intervals)")
                    for i in range(quick_checks):
                        time.sleep(quick_interval)
                        # 使用智能進程名檢測
                        smart_names = self._get_smart_process_names(command)
                        game_processes = self._find_game_processes(smart_names)
                        if game_processes:
                            wait_time = (i + 1) * quick_interval
                            logger.info(f"Game launcher mode: Found {len(game_processes)} game process(es) after {wait_time:.1f}s (quick detection)")
                            self.state_manager.set_process_instance(ProcessType.GAME, None)
                            self.state_manager.set_process_state(ProcessType.GAME, ProcessState.RUNNING, {
                                'launcher_mode': True,
                                'detected_processes': [proc.pid for proc in game_processes],
                                'command': command,
                                'start_time': time.time(),
                                'detection_time': wait_time
                            })
                            logger.info("Game started successfully via launcher mode (quick detection)")
                            return True
                    
                    # 第二階段：常規檢查（剩餘時間，每1秒檢查一次）
                    remaining_time = max_wait_time - quick_check_time
                    regular_interval = 1.0
                    regular_checks = int(remaining_time / regular_interval)
                    
                    logger.info("Game launcher mode: Phase 2 - Regular detection (1s intervals)")
                    for i in range(regular_checks):
                        time.sleep(regular_interval)
                        # 使用智能進程名檢測
                        smart_names = self._get_smart_process_names(command)
                        game_processes = self._find_game_processes(smart_names)
                        if game_processes:
                            wait_time = quick_check_time + (i + 1) * regular_interval
                            logger.info(f"Game launcher mode: Found {len(game_processes)} game process(es) after {wait_time:.1f}s (regular detection)")
                            self.state_manager.set_process_instance(ProcessType.GAME, None)
                            self.state_manager.set_process_state(ProcessType.GAME, ProcessState.RUNNING, {
                                'launcher_mode': True,
                                'detected_processes': [proc.pid for proc in game_processes],
                                'command': command,
                                'start_time': time.time(),
                                'detection_time': wait_time
                            })
                            logger.info("Game started successfully via launcher mode (regular detection)")
                            return True
                    
                    # 等待超時，沒有找到遊戲進程
                    logger.warning(f"Game launcher mode: No game processes found after {max_wait_time}s")
                    logger.info("Game launcher mode: This could indicate:")
                    logger.info("  1. Game takes longer than usual to start")
                    logger.info("  2. Game executable name is different from expected")
                    logger.info("  3. Game startup failed silently")
                    
                    self.state_manager.set_process_state(ProcessType.GAME, ProcessState.ERROR, {
                        'return_code': return_code,
                        'command': command,
                        'error_time': time.time(),
                        'error_type': 'launcher_timeout',
                        'max_wait_time': max_wait_time
                    })
                    return False
                    
                else:
                    # 進程異常退出
                    self.state_manager.set_process_state(ProcessType.GAME, ProcessState.ERROR, {
                        'return_code': return_code,
                        'command': command,
                        'error_time': time.time(),
                        'error_type': 'abnormal_exit'
                    })
                    logger.error(f"Game process failed to start, abnormal return code: {return_code}")
                    return False
                    
            except Exception as e:
                self.state_manager.set_process_state(ProcessType.GAME, ProcessState.ERROR, {
                    'exception': str(e),
                    'command': command,
                    'error_time': time.time()
                })
                logger.error(f"Error starting game process: {e}")
                return False
    
    def stop_game_process(self, timeout: float = 10.0) -> bool:
        """線程安全的停止遊戲進程"""
        with self._operation_lock:
            try:
                game_instance = self.state_manager.get_process_instance(ProcessType.GAME)
                
                # 如果沒有管理的進程實例，嘗試找到系統中的遊戲進程
                if not game_instance:
                    logger.info("No managed game process found, searching for external game processes...")
                    game_processes = self._find_game_processes()
                    
                    if game_processes:
                        logger.info(f"SCHEDULED RESTART: Found {len(game_processes)} external game process(es) to terminate...")
                        success = True
                        for proc in game_processes:
                            try:
                                logger.info(f"SCHEDULED RESTART: Terminating external game process PID {proc.pid} ({proc.name()})")
                                proc.terminate()
                                try:
                                    proc.wait(timeout=timeout/len(game_processes))
                                    logger.info(f"SCHEDULED RESTART: Game process PID {proc.pid} terminated gracefully")
                                except:
                                    proc.kill()
                                    logger.warning(f"SCHEDULED RESTART: Game process PID {proc.pid} killed forcefully")
                            except Exception as e:
                                logger.error(f"SCHEDULED RESTART: Error terminating game process PID {proc.pid}: {e}")
                                success = False
                        
                        self.state_manager.set_process_state(ProcessType.GAME, ProcessState.STOPPED)
                        logger.info(f"SCHEDULED RESTART: External game termination completed, success={success}")
                        return success
                    else:
                        logger.warning("SCHEDULED RESTART: No game processes found in system (game may not be running)")
                        self.state_manager.set_process_state(ProcessType.GAME, ProcessState.STOPPED)
                        return True
                
                # 設置狀態為停止中
                self.state_manager.set_process_state(ProcessType.GAME, ProcessState.STOPPING)
                
                # 嘗試優雅停止
                if self.state_manager.is_process_alive(ProcessType.GAME):
                    game_instance.terminate()
                    
                    # 等待進程結束
                    try:
                        game_instance.wait(timeout=timeout)
                        logger.info("Game process terminated gracefully")
                    except subprocess.TimeoutExpired:
                        # 強制殺死進程
                        logger.warning("Game process did not terminate gracefully, killing...")
                        game_instance.kill()
                        game_instance.wait(timeout=2.0)
                
                # 清理狀態
                self.state_manager.set_process_instance(ProcessType.GAME, None)
                self.state_manager.set_process_state(ProcessType.GAME, ProcessState.STOPPED, {
                    'stop_time': time.time()
                })
                
                return True
                
            except Exception as e:
                self.state_manager.set_process_state(ProcessType.GAME, ProcessState.ERROR, {
                    'exception': str(e),
                    'error_time': time.time()
                })
                logger.error(f"Error stopping game process: {e}")
                return False
    
    def _get_smart_process_names(self, command: List[str]) -> List[str]:
        """根據啟動命令智能推斷要查找的進程名"""
        if not command:
            return ["LastWar.exe", "lastwar.exe"]
        
        command_name = os.path.basename(command[0])
        
        # 如果是Python腳本，查找Python進程
        if command_name.lower() in ["python", "python.exe"] or command[0].lower().endswith('.py'):
            return ["python.exe", "python"]
        
        # 如果命令看起來像是遊戲可執行檔
        if "lastwar" in command_name.lower():
            return ["LastWar.exe", "lastwar.exe", command_name]
        
        # 默認遊戲進程名 + 命令名
        return ["LastWar.exe", "lastwar.exe", command_name]
    
    def _find_game_processes(self, game_process_names=None):
        """查找系統中的遊戲進程"""
        try:
            import psutil
            game_processes = []
            
            # 如果沒有提供遊戲進程名，使用默認值
            if not game_process_names:
                game_process_names = ["LastWar.exe", "lastwar.exe"]
            elif isinstance(game_process_names, str):
                game_process_names = [game_process_names]
            
            logger.info(f"SCHEDULED RESTART: Scanning system for game processes: {game_process_names}")
            
            # 計算總進程數用於調試
            total_processes = 0
            matched_processes = 0
            
            for proc in psutil.process_iter(['pid', 'name']):
                total_processes += 1
                try:
                    if proc.info['name'] and any(proc.info['name'].lower() == name.lower() for name in game_process_names):
                        # 轉換為 psutil.Process 對象以便後續操作
                        game_process = psutil.Process(proc.info['pid'])
                        game_processes.append(game_process)
                        matched_processes += 1
                        logger.info(f"SCHEDULED RESTART: ✓ Found target game process: {proc.info['name']} (PID: {proc.info['pid']})")
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
            
            logger.info(f"SCHEDULED RESTART: Process scan completed - Scanned {total_processes} processes, found {matched_processes} game processes")
            
            if not game_processes:
                logger.warning(f"SCHEDULED RESTART: No game processes found matching {game_process_names}")
                logger.info("SCHEDULED RESTART: This could mean:")
                logger.info("  1. Game is not currently running")
                logger.info("  2. Game process name has changed")
                logger.info("  3. Game was started with a different executable name")
            
            return game_processes
        except Exception as e:
            logger.error(f"SCHEDULED RESTART: Error during game process scan: {e}")
            import traceback
            logger.error(f"SCHEDULED RESTART: Scan traceback: {traceback.format_exc()}")
            return []
    
    def restart_bot_process(self, command: list, cwd: str = None, **kwargs) -> bool:
        """線程安全的重啟 Bot 進程"""
        with self._operation_lock:
            logger.info("Restarting bot process...")
            if self.stop_bot_process():
                time.sleep(1.0)  # 等待清理完成
                return self.start_bot_process(command, cwd, **kwargs)
            return False
    
    def restart_game_process(self, command: list, cwd: str = None, **kwargs) -> bool:
        """線程安全的重啟遊戲進程"""
        with self._operation_lock:
            logger.info("Restarting game process...")
            if self.stop_game_process():
                time.sleep(1.0)  # 等待清理完成
                return self.start_game_process(command, cwd, **kwargs)
            return False
    
    def get_process_status(self, process_type: ProcessType) -> Dict[str, Any]:
        """獲取進程狀態信息"""
        return {
            'state': self.state_manager.get_process_state(process_type),
            'alive': self.state_manager.is_process_alive(process_type),
            'instance': self.state_manager.get_process_instance(process_type),
            'metadata': self.state_manager.get_process_metadata(process_type)
        }

class ThreadSafeMonitor:
    """
    線程安全的監控器
    包裝現有的監控邏輯，確保線程安全
    """
    
    def __init__(self, process_manager: ThreadSafeProcessManager):
        self.process_manager = process_manager
        self.state_manager = state_manager
        self._monitor_thread = None
        self._callbacks = {}
        
    def start_monitoring(self, interval: float = 5.0) -> None:
        """開始監控"""
        if self._monitor_thread and self._monitor_thread.is_alive():
            logger.warning("Monitor thread is already running")
            return
        
        self.state_manager.start_monitoring()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(interval,),
            daemon=True,
            name="ProcessMonitor"
        )
        self._monitor_thread.start()
        
        # 註冊線程到狀態管理器
        self.state_manager.register_thread(
            "process_monitor",
            self._monitor_thread,
            self.state_manager.get_monitoring_flag()
        )
        
        logger.info("Process monitoring started")
    
    def stop_monitoring(self) -> None:
        """停止監控"""
        self.state_manager.stop_monitoring()
        
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=5.0)
            if self._monitor_thread.is_alive():
                logger.warning("Monitor thread did not stop gracefully")
            else:
                logger.info("Process monitoring stopped")
    
    def add_callback(self, event_type: str, callback: Callable) -> None:
        """添加監控回調"""
        if event_type not in self._callbacks:
            self._callbacks[event_type] = []
        self._callbacks[event_type].append(callback)
        logger.info(f"Monitor callback added for {event_type}")
    
    def remove_callback(self, event_type: str, callback: Callable) -> None:
        """移除監控回調"""
        if event_type in self._callbacks:
            try:
                self._callbacks[event_type].remove(callback)
                logger.info(f"Monitor callback removed for {event_type}")
            except ValueError:
                pass
    
    def _monitor_loop(self, interval: float) -> None:
        """監控循環（在獨立線程中運行）"""
        logger.info(f"Monitor loop started with {interval}s interval")
        
        while self.state_manager.is_monitoring():
            try:
                # 檢查 Bot 進程
                self._check_process(ProcessType.BOT)
                
                # 檢查遊戲進程
                self._check_process(ProcessType.GAME)
                
                # 檢查控制客戶端
                self._check_process(ProcessType.CONTROL_CLIENT)
                
                # 等待下次檢查
                time.sleep(interval)
                
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
                time.sleep(interval)
        
        logger.info("Monitor loop ended")
    
    def _check_process(self, process_type: ProcessType) -> None:
        """檢查單個進程狀態"""
        try:
            current_state = self.state_manager.get_process_state(process_type)
            is_alive = self.state_manager.is_process_alive(process_type)
            
            # 狀態不一致檢查
            if current_state == ProcessState.RUNNING and not is_alive:
                logger.warning(f"Process {process_type.value} marked as running but not alive")
                self.state_manager.set_process_state(process_type, ProcessState.ERROR, {
                    'detection_time': time.time(),
                    'reason': 'process_died_unexpectedly'
                })
                self._trigger_callback('process_died', {
                    'process_type': process_type,
                    'detection_time': time.time()
                })
            
            elif current_state in [ProcessState.STARTING, ProcessState.STOPPING]:
                # 檢查是否超時
                metadata = self.state_manager.get_process_metadata(process_type)
                last_update = metadata.get('last_state_change', 0)
                if time.time() - last_update > 30:  # 30秒超時
                    logger.warning(f"Process {process_type.value} stuck in {current_state.value} state")
                    self.state_manager.set_process_state(process_type, ProcessState.ERROR, {
                        'detection_time': time.time(),
                        'reason': f'stuck_in_{current_state.value}'
                    })
                    self._trigger_callback('process_timeout', {
                        'process_type': process_type,
                        'stuck_state': current_state,
                        'detection_time': time.time()
                    })
                    
        except Exception as e:
            logger.error(f"Error checking process {process_type.value}: {e}")
    
    def _trigger_callback(self, event_type: str, data: Dict[str, Any]) -> None:
        """觸發回調函數"""
        callbacks = self._callbacks.get(event_type, [])
        for callback in callbacks:
            try:
                callback(data)
            except Exception as e:
                logger.error(f"Error in callback for {event_type}: {e}")

class ThreadSafeRemoteControl:
    """
    線程安全的遠端控制包裝器
    """
    
    def __init__(self, process_manager: ThreadSafeProcessManager):
        self.process_manager = process_manager
        self.state_manager = state_manager
        self._client_instance = None
        self._connection_lock = threading.RLock()
    
    def start_remote_client(self, server_url: str, client_key: str) -> bool:
        """啟動遠端控制客戶端"""
        with self._connection_lock:
            try:
                # 檢查是否已連接
                if self._client_instance and hasattr(self._client_instance, 'connected'):
                    if getattr(self._client_instance, 'connected', False):
                        logger.warning("Remote control client is already connected")
                        return True
                
                # 設置狀態為啟動中
                self.state_manager.set_process_state(ProcessType.CONTROL_CLIENT, ProcessState.STARTING)
                
                # 這裡應該是實際的 Socket.IO 客戶端啟動邏輯
                # 由於原始代碼中的 ControlClient 類比較複雜，這裡提供一個接口
                
                # 模擬客戶端實例（實際實現時需要替換）
                self._client_instance = self._create_socketio_client(server_url, client_key)
                
                # 註冊客戶端實例
                self.state_manager.set_process_instance(ProcessType.CONTROL_CLIENT, self._client_instance)
                self.state_manager.set_process_state(ProcessType.CONTROL_CLIENT, ProcessState.RUNNING, {
                    'server_url': server_url,
                    'start_time': time.time()
                })
                
                logger.info("Remote control client started")
                return True
                
            except Exception as e:
                self.state_manager.set_process_state(ProcessType.CONTROL_CLIENT, ProcessState.ERROR, {
                    'exception': str(e),
                    'server_url': server_url,
                    'error_time': time.time()
                })
                logger.error(f"Error starting remote control client: {e}")
                return False
    
    def stop_remote_client(self) -> bool:
        """停止遠端控制客戶端"""
        with self._connection_lock:
            try:
                if not self._client_instance:
                    logger.info("No remote control client to stop")
                    self.state_manager.set_process_state(ProcessType.CONTROL_CLIENT, ProcessState.STOPPED)
                    return True
                
                self.state_manager.set_process_state(ProcessType.CONTROL_CLIENT, ProcessState.STOPPING)
                
                # 斷開連接
                if hasattr(self._client_instance, 'disconnect'):
                    self._client_instance.disconnect()
                
                # 清理狀態
                self.state_manager.set_process_instance(ProcessType.CONTROL_CLIENT, None)
                self.state_manager.set_process_state(ProcessType.CONTROL_CLIENT, ProcessState.STOPPED, {
                    'stop_time': time.time()
                })
                
                self._client_instance = None
                logger.info("Remote control client stopped")
                return True
                
            except Exception as e:
                self.state_manager.set_process_state(ProcessType.CONTROL_CLIENT, ProcessState.ERROR, {
                    'exception': str(e),
                    'error_time': time.time()
                })
                logger.error(f"Error stopping remote control client: {e}")
                return False
    
    def _create_socketio_client(self, server_url: str, client_key: str):
        """創建 Socket.IO 客戶端（佔位符方法）"""
        # 這個方法需要在實際集成時實現
        # 應該返回配置好的 Socket.IO 客戶端實例
        class MockClient:
            def __init__(self, url, key):
                self.url = url
                self.key = key
                self.connected = True
            
            def disconnect(self):
                self.connected = False
        
        return MockClient(server_url, client_key)

# 創建全局實例
thread_safe_process_manager = ThreadSafeProcessManager()
thread_safe_monitor = ThreadSafeMonitor(thread_safe_process_manager)
thread_safe_remote_control = ThreadSafeRemoteControl(thread_safe_process_manager)
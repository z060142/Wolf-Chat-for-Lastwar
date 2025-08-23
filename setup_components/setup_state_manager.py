#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Setup State Manager
集中管理 Setup.py 的所有應用狀態，消除全局變數和競態條件
"""

import threading
import time
from typing import Dict, Any, Optional
from enum import Enum
import logging

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ProcessType(Enum):
    """進程類型枚舉"""
    BOT = "bot"
    GAME = "game"
    CONTROL_CLIENT = "control_client"
    MONITOR_THREAD = "monitor_thread"
    SCHEDULER_THREAD = "scheduler_thread"

class ProcessState(Enum):
    """進程狀態枚舉"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"
    UNKNOWN = "unknown"

class ConfigType(Enum):
    """配置類型枚舉"""
    ENV_DATA = "env_data"
    CONFIG_DATA = "config_data"
    REMOTE_DATA = "remote_data"

class SetupStateManager:
    """
    Setup.py 的集中狀態管理器
    
    主要功能：
    1. 線程安全的狀態訪問和更新
    2. 進程狀態管理
    3. 配置狀態管理
    4. 線程狀態管理
    5. 狀態變更通知
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """單例模式實現"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(SetupStateManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        """初始化狀態管理器"""
        if hasattr(self, '_initialized'):
            return
            
        self._initialized = True
        
        # 狀態鎖 - 每種狀態類型都有獨立的鎖
        self._process_lock = threading.RLock()
        self._config_lock = threading.RLock()
        self._thread_lock = threading.RLock()
        self._observers_lock = threading.RLock()
        
        # 進程狀態存儲
        self._process_instances: Dict[ProcessType, Any] = {}
        self._process_states: Dict[ProcessType, ProcessState] = {}
        self._process_metadata: Dict[ProcessType, Dict[str, Any]] = {}
        
        # 配置狀態存儲
        self._config_data: Dict[ConfigType, Dict[str, Any]] = {
            ConfigType.ENV_DATA: {},
            ConfigType.CONFIG_DATA: {},
            ConfigType.REMOTE_DATA: {}
        }
        self._config_dirty_flags: Dict[ConfigType, bool] = {
            ConfigType.ENV_DATA: False,
            ConfigType.CONFIG_DATA: False,
            ConfigType.REMOTE_DATA: False
        }
        
        # 線程狀態管理
        self._thread_instances: Dict[str, threading.Thread] = {}
        self._thread_flags: Dict[str, threading.Event] = {}
        
        # 狀態觀察者
        self._state_observers: Dict[str, list] = {
            'process_state_changed': [],
            'config_changed': [],
            'thread_state_changed': []
        }
        
        # 全局標誌
        self._keep_monitoring_flag = threading.Event()
        self._shutdown_flag = threading.Event()
        
        logger.info("SetupStateManager initialized")
    
    # ================================================
    # 進程狀態管理
    # ================================================
    
    def get_process_instance(self, process_type: ProcessType) -> Optional[Any]:
        """獲取進程實例（線程安全）"""
        with self._process_lock:
            return self._process_instances.get(process_type)
    
    def set_process_instance(self, process_type: ProcessType, instance: Any) -> None:
        """設置進程實例（線程安全）"""
        with self._process_lock:
            old_instance = self._process_instances.get(process_type)
            self._process_instances[process_type] = instance
            
            # 更新狀態
            if instance is None:
                self._process_states[process_type] = ProcessState.STOPPED
            else:
                self._process_states[process_type] = ProcessState.RUNNING
            
            # 記錄元數據
            if process_type not in self._process_metadata:
                self._process_metadata[process_type] = {}
            self._process_metadata[process_type]['last_update'] = time.time()
            self._process_metadata[process_type]['instance_id'] = id(instance) if instance else None
            
            # 通知觀察者
            self._notify_observers('process_state_changed', {
                'process_type': process_type,
                'old_instance': old_instance,
                'new_instance': instance,
                'new_state': self._process_states[process_type]
            })
            
            logger.info(f"Process {process_type.value} instance updated: {instance is not None}")
    
    def get_process_state(self, process_type: ProcessType) -> ProcessState:
        """獲取進程狀態"""
        with self._process_lock:
            return self._process_states.get(process_type, ProcessState.UNKNOWN)
    
    def set_process_state(self, process_type: ProcessType, state: ProcessState, metadata: Dict[str, Any] = None) -> None:
        """設置進程狀態"""
        with self._process_lock:
            old_state = self._process_states.get(process_type, ProcessState.UNKNOWN)
            self._process_states[process_type] = state
            
            # 更新元數據
            if process_type not in self._process_metadata:
                self._process_metadata[process_type] = {}
            self._process_metadata[process_type]['last_state_change'] = time.time()
            if metadata:
                self._process_metadata[process_type].update(metadata)
            
            # 通知觀察者
            self._notify_observers('process_state_changed', {
                'process_type': process_type,
                'old_state': old_state,
                'new_state': state,
                'metadata': metadata
            })
            
            logger.info(f"Process {process_type.value} state changed: {old_state.value} -> {state.value}")
    
    def get_process_metadata(self, process_type: ProcessType) -> Dict[str, Any]:
        """獲取進程元數據"""
        with self._process_lock:
            return self._process_metadata.get(process_type, {}).copy()
    
    def is_process_alive(self, process_type: ProcessType) -> bool:
        """檢查進程是否存活"""
        with self._process_lock:
            instance = self._process_instances.get(process_type)
            
            # 檢查是否為啟動器模式
            metadata = self._process_metadata.get(process_type, {})
            if metadata.get('launcher_mode') and process_type == ProcessType.GAME:
                # 啟動器模式：通過系統進程檢測
                return self._check_launcher_mode_game_alive(metadata)
            
            if instance is None:
                return False
            
            # 針對不同類型的進程實例進行檢查
            if hasattr(instance, 'poll'):  # subprocess.Popen
                return instance.poll() is None
            elif hasattr(instance, 'is_alive'):  # threading.Thread or multiprocessing.Process
                return instance.is_alive()
            elif hasattr(instance, 'connected'):  # Socket.IO client
                return getattr(instance, 'connected', False)
            else:
                return True  # 未知類型，假設存活
    
    def _check_launcher_mode_game_alive(self, metadata: Dict[str, Any]) -> bool:
        """檢查啟動器模式下的遊戲是否存活"""
        try:
            import psutil
            
            # 從元數據中獲取檢測到的進程PIDs
            detected_pids = metadata.get('detected_processes', [])
            
            # 檢查這些PID是否還存在且為遊戲進程
            for pid in detected_pids:
                try:
                    proc = psutil.Process(pid)
                    # 檢查進程名稱是否匹配遊戲進程
                    if proc.name().lower() in ["lastwar.exe", "last war.exe"]:
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
            
            # 如果原始PID檢查失敗，進行全系統掃描
            game_process_names = ["LastWar.exe", "lastwar.exe", "Last War.exe"]
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if proc.info['name'] and any(proc.info['name'].lower() == name.lower() for name in game_process_names):
                        # 更新檢測到的進程列表
                        metadata['detected_processes'] = [proc.info['pid']]
                        self._process_metadata[ProcessType.GAME] = metadata
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
            
            # 沒有找到遊戲進程，更新狀態
            logger.info("Launcher mode: Game process no longer detected, marking as stopped")
            self._process_states[ProcessType.GAME] = ProcessState.STOPPED
            return False
            
        except Exception as e:
            logger.error(f"Error checking launcher mode game status: {e}")
            return False
    
    # ================================================
    # 配置狀態管理
    # ================================================
    
    def get_config_data(self, config_type: ConfigType) -> Dict[str, Any]:
        """獲取配置數據（線程安全）"""
        with self._config_lock:
            return self._config_data[config_type].copy()
    
    def set_config_data(self, config_type: ConfigType, data: Dict[str, Any]) -> None:
        """設置配置數據（線程安全）"""
        with self._config_lock:
            old_data = self._config_data[config_type].copy()
            self._config_data[config_type] = data.copy()
            self._config_dirty_flags[config_type] = True
            
            # 通知觀察者
            self._notify_observers('config_changed', {
                'config_type': config_type,
                'old_data': old_data,
                'new_data': data
            })
            
            logger.info(f"Config {config_type.value} updated")
    
    def update_config_data(self, config_type: ConfigType, updates: Dict[str, Any]) -> None:
        """部分更新配置數據"""
        with self._config_lock:
            old_data = self._config_data[config_type].copy()
            self._config_data[config_type].update(updates)
            self._config_dirty_flags[config_type] = True
            
            # 通知觀察者
            self._notify_observers('config_changed', {
                'config_type': config_type,
                'old_data': old_data,
                'new_data': self._config_data[config_type].copy(),
                'updates': updates
            })
            
            logger.info(f"Config {config_type.value} partially updated: {list(updates.keys())}")
    
    def is_config_dirty(self, config_type: ConfigType) -> bool:
        """檢查配置是否有未保存的更改"""
        with self._config_lock:
            return self._config_dirty_flags[config_type]
    
    def mark_config_clean(self, config_type: ConfigType) -> None:
        """標記配置為已保存狀態"""
        with self._config_lock:
            self._config_dirty_flags[config_type] = False
            logger.info(f"Config {config_type.value} marked as clean")
    
    def get_all_dirty_configs(self) -> list:
        """獲取所有有未保存更改的配置類型"""
        with self._config_lock:
            return [config_type for config_type, dirty in self._config_dirty_flags.items() if dirty]
    
    # ================================================
    # 線程狀態管理
    # ================================================
    
    def register_thread(self, thread_name: str, thread_instance: threading.Thread, 
                       control_flag: threading.Event = None) -> None:
        """註冊線程"""
        with self._thread_lock:
            self._thread_instances[thread_name] = thread_instance
            if control_flag:
                self._thread_flags[thread_name] = control_flag
            
            logger.info(f"Thread {thread_name} registered")
    
    def get_thread_instance(self, thread_name: str) -> Optional[threading.Thread]:
        """獲取線程實例"""
        with self._thread_lock:
            return self._thread_instances.get(thread_name)
    
    def get_thread_flag(self, thread_name: str) -> Optional[threading.Event]:
        """獲取線程控制標誌"""
        with self._thread_lock:
            return self._thread_flags.get(thread_name)
    
    def stop_thread(self, thread_name: str, timeout: float = 5.0) -> bool:
        """停止線程"""
        with self._thread_lock:
            thread = self._thread_instances.get(thread_name)
            flag = self._thread_flags.get(thread_name)
            
            if flag:
                flag.clear()  # 停止線程執行
            
            if thread and thread.is_alive():
                thread.join(timeout)
                success = not thread.is_alive()
                if success:
                    logger.info(f"Thread {thread_name} stopped successfully")
                else:
                    logger.warning(f"Thread {thread_name} did not stop within {timeout}s")
                return success
            
            return True
    
    def stop_all_threads(self, timeout: float = 10.0) -> bool:
        """停止所有線程"""
        with self._thread_lock:
            thread_names = list(self._thread_instances.keys())
            
        success = True
        for thread_name in thread_names:
            if not self.stop_thread(thread_name, timeout / len(thread_names)):
                success = False
        
        return success
    
    # ================================================
    # 全局標誌管理
    # ================================================
    
    def get_monitoring_flag(self) -> threading.Event:
        """獲取監控標誌"""
        return self._keep_monitoring_flag
    
    def start_monitoring(self) -> None:
        """開始監控"""
        self._keep_monitoring_flag.set()
        logger.info("Monitoring started")
    
    def stop_monitoring(self) -> None:
        """停止監控"""
        self._keep_monitoring_flag.clear()
        logger.info("Monitoring stopped")
    
    def is_monitoring(self) -> bool:
        """檢查是否正在監控"""
        return self._keep_monitoring_flag.is_set()
    
    def get_shutdown_flag(self) -> threading.Event:
        """獲取關閉標誌"""
        return self._shutdown_flag
    
    def initiate_shutdown(self) -> None:
        """開始關閉流程"""
        self._shutdown_flag.set()
        self.stop_monitoring()
        logger.info("Shutdown initiated")
    
    def is_shutting_down(self) -> bool:
        """檢查是否正在關閉"""
        return self._shutdown_flag.is_set()
    
    # ================================================
    # 觀察者模式支持
    # ================================================
    
    def add_observer(self, event_type: str, callback) -> None:
        """添加狀態變更觀察者"""
        with self._observers_lock:
            if event_type not in self._state_observers:
                self._state_observers[event_type] = []
            self._state_observers[event_type].append(callback)
            logger.info(f"Observer added for {event_type}")
    
    def remove_observer(self, event_type: str, callback) -> None:
        """移除狀態變更觀察者"""
        with self._observers_lock:
            if event_type in self._state_observers:
                try:
                    self._state_observers[event_type].remove(callback)
                    logger.info(f"Observer removed for {event_type}")
                except ValueError:
                    pass
    
    def _notify_observers(self, event_type: str, data: Dict[str, Any]) -> None:
        """通知觀察者（內部方法）"""
        with self._observers_lock:
            observers = self._state_observers.get(event_type, []).copy()
        
        for callback in observers:
            try:
                callback(data)
            except Exception as e:
                logger.error(f"Error in observer callback for {event_type}: {e}")
    
    # ================================================
    # 狀態快照和調試
    # ================================================
    
    def get_state_snapshot(self) -> Dict[str, Any]:
        """獲取當前所有狀態的快照"""
        snapshot = {
            'timestamp': time.time(),
            'processes': {},
            'configs': {},
            'threads': {},
            'flags': {
                'monitoring': self.is_monitoring(),
                'shutting_down': self.is_shutting_down()
            }
        }
        
        # 進程狀態
        with self._process_lock:
            for process_type in ProcessType:
                snapshot['processes'][process_type.value] = {
                    'state': self.get_process_state(process_type).value,
                    'alive': self.is_process_alive(process_type),
                    'metadata': self.get_process_metadata(process_type)
                }
        
        # 配置狀態
        with self._config_lock:
            for config_type in ConfigType:
                snapshot['configs'][config_type.value] = {
                    'dirty': self.is_config_dirty(config_type),
                    'data_size': len(self._config_data[config_type])
                }
        
        # 線程狀態
        with self._thread_lock:
            for thread_name, thread in self._thread_instances.items():
                snapshot['threads'][thread_name] = {
                    'alive': thread.is_alive() if thread else False,
                    'daemon': thread.daemon if thread else None
                }
        
        return snapshot
    
    def log_state_summary(self) -> None:
        """記錄狀態摘要到日誌"""
        snapshot = self.get_state_snapshot()
        logger.info(f"State Summary: {snapshot}")
    
    # ================================================
    # 清理和重置
    # ================================================
    
    def cleanup(self) -> None:
        """清理所有資源"""
        logger.info("Starting state manager cleanup")
        
        # 停止所有線程
        self.stop_all_threads()
        
        # 清理進程實例
        with self._process_lock:
            self._process_instances.clear()
            self._process_states.clear()
            self._process_metadata.clear()
        
        # 清理配置
        with self._config_lock:
            for config_type in ConfigType:
                self._config_data[config_type].clear()
                self._config_dirty_flags[config_type] = False
        
        # 清理線程
        with self._thread_lock:
            self._thread_instances.clear()
            self._thread_flags.clear()
        
        # 清理觀察者
        with self._observers_lock:
            self._state_observers.clear()
        
        logger.info("State manager cleanup completed")

# 全局實例（單例）
state_manager = SetupStateManager()
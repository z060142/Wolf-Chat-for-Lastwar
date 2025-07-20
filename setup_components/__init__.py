#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Setup Components Package
Wolf Chat Setup 重構組件包

這個包包含了 Setup.py 重構的所有組件：
- 狀態管理器
- 線程安全包裝器  
- 配置事務管理器
"""

# 導入主要組件
from .setup_state_manager import (
    state_manager, 
    SetupStateManager,
    ProcessType, 
    ProcessState, 
    ConfigType
)

from .setup_threading_safe import (
    thread_safe_process_manager,
    thread_safe_monitor,
    thread_safe_remote_control,
    ThreadSafeProcessManager,
    ThreadSafeMonitor,
    ThreadSafeRemoteControl
)

from .setup_config_transaction import (
    config_transaction_manager,
    ConfigTransactionManager,
    ConfigTransaction
)

# 版本信息
__version__ = "1.0.0"
__author__ = "Wolf Chat Refactoring Team"

# 導出的主要接口
__all__ = [
    # 單例實例
    'state_manager',
    'thread_safe_process_manager', 
    'thread_safe_monitor',
    'thread_safe_remote_control',
    'config_transaction_manager',
    
    # 類定義
    'SetupStateManager',
    'ThreadSafeProcessManager',
    'ThreadSafeMonitor', 
    'ThreadSafeRemoteControl',
    'ConfigTransactionManager',
    'ConfigTransaction',
    
    # 枚舉類型
    'ProcessType',
    'ProcessState',
    'ConfigType'
]

# 便利函數
def get_all_components():
    """獲取所有組件的狀態摘要"""
    return {
        'state_manager': state_manager.get_state_snapshot(),
        'process_manager': {
            'available': thread_safe_process_manager is not None,
            'class': type(thread_safe_process_manager).__name__
        },
        'config_transaction': {
            'available': config_transaction_manager is not None,
            'current_transaction': config_transaction_manager.get_transaction_status()
        }
    }

def cleanup_all_components():
    """清理所有組件"""
    try:
        # 停止監控
        thread_safe_monitor.stop_monitoring()
        
        # 停止遠端控制
        thread_safe_remote_control.stop_remote_client()
        
        # 清理狀態管理器
        state_manager.cleanup()
        
        print("所有組件已清理完成")
        return True
    except Exception as e:
        print(f"組件清理時發生錯誤: {e}")
        return False
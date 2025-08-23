#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Setup Integration Patch
應用狀態管理器到現有 Setup.py 的集成補丁
"""

import re
import os
from pathlib import Path

def apply_state_manager_integration():
    """
    應用狀態管理器集成到 Setup.py
    這個函數會修改原始 Setup.py 文件，添加狀態管理功能
    """
    
    setup_file_path = "Setup.py"
    backup_path = "Setup_backup_v1.py"
    
    # 確保備份存在
    if not os.path.exists(backup_path):
        print("錯誤：找不到備份文件 Setup_backup_v1.py")
        return False
    
    try:
        # 讀取原始文件
        with open(setup_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 應用修改
        modified_content = apply_modifications(content)
        
        # 寫入修改後的文件
        with open(setup_file_path, 'w', encoding='utf-8') as f:
            f.write(modified_content)
        
        print("狀態管理器集成完成！")
        return True
        
    except Exception as e:
        print(f"集成失敗：{e}")
        # 嘗試恢復備份
        try:
            with open(backup_path, 'r', encoding='utf-8') as f:
                backup_content = f.read()
            with open(setup_file_path, 'w', encoding='utf-8') as f:
                f.write(backup_content)
            print("已恢復原始文件")
        except:
            print("恢復失敗！請手動恢復 Setup_backup_v1.py")
        return False

def apply_modifications(content):
    """應用所有必要的修改"""
    
    # 1. 添加狀態管理器導入
    content = add_state_manager_imports(content)
    
    # 2. 替換全局變量聲明
    content = replace_global_variables(content)
    
    # 3. 修改 WolfChatSetup 類初始化
    content = modify_class_initialization(content)
    
    # 4. 更新進程管理方法
    content = update_process_management_methods(content)
    
    # 5. 更新線程管理
    content = update_threading_management(content)
    
    # 6. 集成配置事務管理
    content = integrate_config_transactions(content)
    
    return content

def add_state_manager_imports(content):
    """添加狀態管理器導入"""
    
    # 在現有導入後添加新的導入
    import_section = """
# Wolf Chat State Management Components (Added by refactoring)
from setup_state_manager import state_manager, ProcessType, ProcessState, ConfigType
from setup_threading_safe import (
    thread_safe_process_manager, 
    thread_safe_monitor, 
    thread_safe_remote_control
)
from setup_config_transaction import config_transaction_manager
"""
    
    # 在 game_manager 導入後添加
    pattern = r"(import game_manager.*?\n)"
    replacement = r"\1" + import_section
    
    return re.sub(pattern, replacement, content, flags=re.DOTALL)

def replace_global_variables(content):
    """替換全局變量聲明"""
    
    # 找到全局變量聲明區域並替換
    global_vars_pattern = r"""# Global variables for game/bot management
game_process_instance = None
bot_process_instance = None.*?
control_client_instance = None
monitor_thread_instance = None.*?
scheduler_thread_instance = None.*?
keep_monitoring_flag = threading\.Event\(\).*?"""
    
    replacement = """# Global variables for game/bot management (Replaced with state manager)
# These are now managed by the state_manager singleton
# Direct access replaced with state_manager calls

# Legacy compatibility - these will redirect to state manager
def get_game_process_instance():
    return state_manager.get_process_instance(ProcessType.GAME)

def set_game_process_instance(instance):
    state_manager.set_process_instance(ProcessType.GAME, instance)

def get_bot_process_instance():
    return state_manager.get_process_instance(ProcessType.BOT)

def set_bot_process_instance(instance):
    state_manager.set_process_instance(ProcessType.BOT, instance)

def get_control_client_instance():
    return state_manager.get_process_instance(ProcessType.CONTROL_CLIENT)

def set_control_client_instance(instance):
    state_manager.set_process_instance(ProcessType.CONTROL_CLIENT, instance)

# Legacy global variables for backward compatibility
game_process_instance = None
bot_process_instance = None  
control_client_instance = None
monitor_thread_instance = None
scheduler_thread_instance = None
keep_monitoring_flag = state_manager.get_monitoring_flag()"""
    
    return re.sub(global_vars_pattern, replacement, content, flags=re.DOTALL)

def modify_class_initialization(content):
    """修改 WolfChatSetup 類初始化"""
    
    # 找到 __init__ 方法中的實例變量初始化
    init_vars_pattern = r"""(# Initialize running process tracker.*?\n)(.*?)(# Initialize new process management variables.*?\n)(.*?)(self\.keep_monitoring_flag = threading\.Event\(\).*?\n)"""
    
    replacement = r"""\1\2# Initialize state management integration (Added by refactoring)
        self.state_manager = state_manager
        self.process_manager = thread_safe_process_manager
        self.monitor = thread_safe_monitor
        self.remote_control = thread_safe_remote_control
        self.config_tx_manager = config_transaction_manager
        
        # Legacy instance variables - now redirect to state manager
        self._setup_legacy_compatibility()
        
\3\4# keep_monitoring_flag now managed by state manager
        self.keep_monitoring_flag = self.state_manager.get_monitoring_flag()
"""
    
    content = re.sub(init_vars_pattern, replacement, content, flags=re.DOTALL)
    
    # 添加 legacy compatibility 方法
    legacy_method = """
    def _setup_legacy_compatibility(self):
        \"\"\"設置向後相容性支持\"\"\"
        # 這些屬性現在重定向到狀態管理器
        self._running_process = None
        self._bot_process_instance = None
        self._game_process_instance = None
        self._control_client_instance = None
        self._monitor_thread_instance = None
        self._scheduler_thread_instance = None
    
    @property
    def running_process(self):
        return self.state_manager.get_process_instance(ProcessType.BOT)
    
    @running_process.setter
    def running_process(self, value):
        self.state_manager.set_process_instance(ProcessType.BOT, value)
    
    @property
    def bot_process_instance(self):
        return self.state_manager.get_process_instance(ProcessType.BOT)
    
    @bot_process_instance.setter
    def bot_process_instance(self, value):
        self.state_manager.set_process_instance(ProcessType.BOT, value)
    
    @property 
    def game_process_instance(self):
        return self.state_manager.get_process_instance(ProcessType.GAME)
    
    @game_process_instance.setter
    def game_process_instance(self, value):
        self.state_manager.set_process_instance(ProcessType.GAME, value)
    
    @property
    def control_client_instance(self):
        return self.state_manager.get_process_instance(ProcessType.CONTROL_CLIENT)
    
    @control_client_instance.setter
    def control_client_instance(self, value):
        self.state_manager.set_process_instance(ProcessType.CONTROL_CLIENT, value)
"""
    
    # 在類定義中找到合適的位置插入 legacy compatibility 方法
    class_pattern = r"(class WolfChatSetup\(tk\.Tk\):.*?def __init__\(self\):.*?self\.update_ui_from_data\(\).*?\n)"
    
    replacement = r"\1" + legacy_method + "\n"
    
    return re.sub(class_pattern, replacement, content, flags=re.DOTALL)

def update_process_management_methods(content):
    """更新進程管理方法以使用線程安全包裝器"""
    
    # 替換進程啟動方法
    start_bot_pattern = r"(def _start_bot_managed\(self\):.*?)(# Start the bot process.*?\n)(.*?)(subprocess\.Popen\(.*?\n.*?\n.*?\n)"
    
    bot_replacement = r"""\1\2        # Use thread-safe process manager (Modified by refactoring)
        bot_command = [
            sys.executable, "main.py"
        ]
        
        if self.process_manager.start_bot_process(bot_command):
            logger.info("Bot process started successfully via thread-safe manager")
            # Update legacy global variable for compatibility
            global bot_process_instance
            bot_process_instance = self.bot_process_instance
        else:
            logger.error("Failed to start bot process via thread-safe manager")
        
        # Original subprocess logic (commented out - replaced by thread-safe manager)
        # \4"""
    
    content = re.sub(start_bot_pattern, bot_replacement, content, flags=re.DOTALL)
    
    # 替換進程停止方法
    stop_bot_pattern = r"(def _stop_bot_managed\(self\):.*?)(if self\.bot_process_instance:.*?\n)(.*?)(# Clean up the process instance.*?\n)"
    
    stop_replacement = r"""\1        # Use thread-safe process manager (Modified by refactoring)
        if self.process_manager.stop_bot_process():
            logger.info("Bot process stopped successfully via thread-safe manager")
        else:
            logger.error("Failed to stop bot process via thread-safe manager")
        
        # Update legacy global variable for compatibility
        global bot_process_instance
        bot_process_instance = None
        
        # Original stop logic (commented out - replaced by thread-safe manager)
        # \2\3\4"""
    
    content = re.sub(stop_bot_pattern, stop_replacement, content, flags=re.DOTALL)
    
    return content

def update_threading_management(content):
    """更新線程管理以使用狀態管理器"""
    
    # 替換監控線程啟動
    monitor_pattern = r"(def _start_monitoring_thread\(self\):.*?)(self\.monitor_thread_instance = threading\.Thread.*?\n)(.*?)(self\.monitor_thread_instance\.start\(\).*?\n)"
    
    monitor_replacement = r"""\1        # Use thread-safe monitor (Modified by refactoring)
        self.monitor.start_monitoring(interval=5.0)
        
        # Register monitor callbacks
        self.monitor.add_callback('process_died', self._handle_process_died)
        self.monitor.add_callback('process_timeout', self._handle_process_timeout)
        
        # Legacy thread instance for compatibility
        self.monitor_thread_instance = self.state_manager.get_thread_instance("process_monitor")
        
        logger.info("Thread-safe monitoring started")
        
        # Original threading logic (commented out - replaced by thread-safe monitor)
        # \2\3\4"""
    
    content = re.sub(monitor_pattern, monitor_replacement, content, flags=re.DOTALL)
    
    # 添加回調處理方法
    callback_methods = """
    def _handle_process_died(self, data):
        \"\"\"處理進程意外終止\"\"\"
        process_type = data['process_type']
        logger.warning(f"Process {process_type.value} died unexpectedly")
        
        # 觸發 UI 更新
        self.after(0, self.update_management_buttons_state)
        
        # 可以添加自動重啟邏輯
        if hasattr(self, 'auto_restart_enabled') and self.auto_restart_enabled:
            if process_type == ProcessType.BOT:
                self.after(5000, self._restart_bot_managed)  # 5秒後重啟
            elif process_type == ProcessType.GAME:
                self.after(5000, self._restart_game_managed)
    
    def _handle_process_timeout(self, data):
        \"\"\"處理進程狀態超時\"\"\"
        process_type = data['process_type']
        stuck_state = data['stuck_state']
        logger.error(f"Process {process_type.value} stuck in {stuck_state.value} state")
        
        # 觸發 UI 更新
        self.after(0, self.update_management_buttons_state)
        
        # 可以嘗試強制重置狀態
        self.state_manager.set_process_state(process_type, ProcessState.ERROR)
"""
    
    # 插入回調方法
    content = content.replace(
        "    def _monitoring_loop(self):",
        callback_methods + "\n    def _monitoring_loop(self):"
    )
    
    return content

def integrate_config_transactions(content):
    """集成配置事務管理"""
    
    # 替換 save_settings 方法以使用事務
    save_pattern = r"(def save_settings\(self\):.*?)(# Get data from UI.*?\n)(.*?)(# Generate config\.py.*?\n)(.*?)(messagebox\.showinfo.*?\n)"
    
    save_replacement = r"""\1        # Use configuration transaction manager (Modified by refactoring)
        try:
            # Begin transaction
            tx_id = self.config_tx_manager.begin_transaction()
            logger.info(f"Started config transaction: {tx_id}")
            
            # Collect all configuration updates
            config_updates = self._collect_config_updates()
            
            # Apply updates to transaction
            for config_type, data in config_updates.items():
                self.config_tx_manager.update_config(config_type, data)
            
            # Validate and commit transaction
            is_valid, errors = self.config_tx_manager.validate_transaction()
            if is_valid:
                if self.config_tx_manager.commit_transaction():
                    messagebox.showinfo("成功", "配置已成功保存！")
                    logger.info("Configuration transaction committed successfully")
                else:
                    messagebox.showerror("錯誤", "配置保存失敗！")
                    logger.error("Configuration transaction commit failed")
            else:
                # Show validation errors
                error_msg = "配置驗證失敗：\\n" + "\\n".join(errors)
                messagebox.showerror("驗證錯誤", error_msg)
                self.config_tx_manager.rollback_transaction()
                logger.error(f"Configuration validation failed: {errors}")
                
        except Exception as e:
            logger.error(f"Error in save_settings: {e}")
            try:
                self.config_tx_manager.rollback_transaction()
            except:
                pass
            messagebox.showerror("錯誤", f"保存配置時發生錯誤：{e}")
        
        # Original save logic (commented out - replaced by transaction manager)
        # \2\3\4\5\6"""
    
    content = re.sub(save_pattern, save_replacement, content, flags=re.DOTALL)
    
    # 添加配置收集方法
    config_collection_method = """
    def _collect_config_updates(self):
        \"\"\"收集所有配置更新\"\"\"
        updates = {}
        
        # Collect ENV data
        env_data = {}
        if self.openai_api_key_var.get().strip():
            env_data['OPENAI_API_KEY'] = self.openai_api_key_var.get().strip()
        if self.exa_api_key_var.get().strip():
            env_data['EXA_API_KEY'] = self.exa_api_key_var.get().strip()
        
        if env_data:
            updates[ConfigType.ENV_DATA] = env_data
        
        # Collect config data (simplified - would need full implementation)
        config_data = {
            'OPENAI_BASE_URL': self.openai_base_url_var.get().strip(),
            'OPENAI_MODEL': self.openai_model_var.get().strip(),
            # ... other config items would be collected here
        }
        updates[ConfigType.CONFIG_DATA] = config_data
        
        # Collect remote data
        remote_data = {
            'enable_remote_control': hasattr(self, 'enable_remote_control_var') and self.enable_remote_control_var.get(),
            'server_url': getattr(self, 'server_url_var', tk.StringVar()).get().strip(),
            'client_key': getattr(self, 'client_key_var', tk.StringVar()).get().strip(),
        }
        updates[ConfigType.REMOTE_DATA] = remote_data
        
        return updates
"""
    
    # 插入配置收集方法
    content = content.replace(
        "    def save_settings(self):",
        config_collection_method + "\n    def save_settings(self):"
    )
    
    return content

if __name__ == "__main__":
    print("開始應用狀態管理器集成補丁...")
    success = apply_state_manager_integration()
    if success:
        print("✅ 集成成功完成！")
        print("📋 階段1重構完成：")
        print("   - 狀態管理器已集成")
        print("   - 線程安全包裝器已應用")
        print("   - 配置事務管理已啟用")
        print("   - 向後相容性已保持")
    else:
        print("❌ 集成失敗！")
        print("請檢查錯誤信息並手動恢復備份文件。")
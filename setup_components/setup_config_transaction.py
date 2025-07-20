#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Setup Configuration Transaction Manager
提供原子性的配置更新操作，確保多個配置文件的一致性
"""

import os
import json
import shutil
import tempfile
import time
import logging
import threading
from typing import Dict, Any, List, Optional, Callable
from pathlib import Path
from .setup_state_manager import state_manager, ConfigType

logger = logging.getLogger(__name__)

class ConfigTransaction:
    """
    配置事務類
    管理單個配置事務的生命週期
    """
    
    def __init__(self, transaction_id: str):
        self.transaction_id = transaction_id
        self.start_time = time.time()
        self.operations = []
        self.backups = {}
        self.committed = False
        self.rolled_back = False
        
    def add_operation(self, operation_type: str, config_type: ConfigType, 
                     file_path: str, data: Dict[str, Any]) -> None:
        """添加配置操作到事務"""
        self.operations.append({
            'operation_type': operation_type,
            'config_type': config_type,
            'file_path': file_path,
            'data': data,
            'timestamp': time.time()
        })
    
    def add_backup(self, file_path: str, backup_path: str) -> None:
        """添加備份文件信息"""
        self.backups[file_path] = backup_path
    
    def is_active(self) -> bool:
        """檢查事務是否仍處於活動狀態"""
        return not self.committed and not self.rolled_back

class ConfigTransactionManager:
    """
    配置事務管理器
    確保配置更新的原子性和一致性
    """
    
    def __init__(self):
        self.state_manager = state_manager
        self._transaction_lock = threading.RLock()
        self._current_transaction: Optional[ConfigTransaction] = None
        self._backup_dir = None
        self._validators = {}
        self._pre_commit_hooks = []
        self._post_commit_hooks = []
        self._rollback_hooks = []
        
        # 配置文件路徑映射
        self._config_file_paths = {
            ConfigType.ENV_DATA: ".env",
            ConfigType.CONFIG_DATA: "config.py", 
            ConfigType.REMOTE_DATA: "remote_config.json"
        }
        
        # 創建備份目錄
        self._setup_backup_directory()
        
    def _setup_backup_directory(self) -> None:
        """設置備份目錄"""
        self._backup_dir = Path("config_backups")
        self._backup_dir.mkdir(exist_ok=True)
        logger.info(f"Config backup directory: {self._backup_dir.absolute()}")
    
    def begin_transaction(self) -> str:
        """開始新的配置事務"""
        with self._transaction_lock:
            if self._current_transaction and self._current_transaction.is_active():
                raise RuntimeError("Another transaction is already active")
            
            transaction_id = f"config_tx_{int(time.time() * 1000)}"
            self._current_transaction = ConfigTransaction(transaction_id)
            
            logger.info(f"Configuration transaction started: {transaction_id}")
            return transaction_id
    
    def update_config(self, config_type: ConfigType, data: Dict[str, Any], 
                     merge: bool = True) -> None:
        """在事務中更新配置"""
        with self._transaction_lock:
            if not self._current_transaction or not self._current_transaction.is_active():
                raise RuntimeError("No active transaction")
            
            file_path = self._config_file_paths[config_type]
            
            # 合併或替換數據
            if merge and config_type != ConfigType.CONFIG_DATA:  # config.py 通常是完全替換
                current_data = self.state_manager.get_config_data(config_type)
                merged_data = current_data.copy()
                merged_data.update(data)
                final_data = merged_data
            else:
                final_data = data
            
            # 添加操作到事務
            self._current_transaction.add_operation(
                "update", config_type, file_path, final_data
            )
            
            # 更新內存中的配置
            self.state_manager.set_config_data(config_type, final_data)
            
            logger.info(f"Config update queued in transaction: {config_type.value}")
    
    def validate_transaction(self) -> tuple[bool, List[str]]:
        """驗證事務中的所有配置更改"""
        with self._transaction_lock:
            if not self._current_transaction or not self._current_transaction.is_active():
                raise RuntimeError("No active transaction")
            
            errors = []
            
            # 運行配置驗證器
            for operation in self._current_transaction.operations:
                config_type = operation['config_type']
                data = operation['data']
                
                validator = self._validators.get(config_type)
                if validator:
                    try:
                        is_valid, validation_errors = validator(data)
                        if not is_valid:
                            errors.extend([f"{config_type.value}: {err}" for err in validation_errors])
                    except Exception as e:
                        errors.append(f"{config_type.value}: Validation error - {e}")
            
            # 檢查配置間的依賴關係
            dependency_errors = self._validate_config_dependencies()
            errors.extend(dependency_errors)
            
            is_valid = len(errors) == 0
            logger.info(f"Transaction validation: {'PASSED' if is_valid else 'FAILED'}")
            if errors:
                for error in errors:
                    logger.error(f"Validation error: {error}")
            
            return is_valid, errors
    
    def commit_transaction(self) -> bool:
        """提交事務，將所有更改寫入文件"""
        with self._transaction_lock:
            if not self._current_transaction or not self._current_transaction.is_active():
                raise RuntimeError("No active transaction")
            
            try:
                # 運行預提交鉤子
                for hook in self._pre_commit_hooks:
                    try:
                        hook(self._current_transaction)
                    except Exception as e:
                        logger.error(f"Pre-commit hook failed: {e}")
                        return False
                
                # 驗證事務
                is_valid, errors = self.validate_transaction()
                if not is_valid:
                    logger.error("Transaction validation failed, cannot commit")
                    return False
                
                # 創建備份
                self._create_backups()
                
                # 執行所有配置文件寫入
                for operation in self._current_transaction.operations:
                    if operation['operation_type'] == 'update':
                        self._write_config_file(
                            operation['config_type'],
                            operation['file_path'],
                            operation['data']
                        )
                
                # 標記配置為乾淨狀態
                for operation in self._current_transaction.operations:
                    self.state_manager.mark_config_clean(operation['config_type'])
                
                # 標記事務為已提交
                self._current_transaction.committed = True
                
                # 運行後提交鉤子
                for hook in self._post_commit_hooks:
                    try:
                        hook(self._current_transaction)
                    except Exception as e:
                        logger.error(f"Post-commit hook failed: {e}")
                
                logger.info(f"Transaction committed successfully: {self._current_transaction.transaction_id}")
                
                # 清理舊備份
                self._cleanup_old_backups()
                
                return True
                
            except Exception as e:
                logger.error(f"Error committing transaction: {e}")
                self.rollback_transaction()
                return False
    
    def rollback_transaction(self) -> bool:
        """回滾事務，恢復所有配置"""
        with self._transaction_lock:
            if not self._current_transaction:
                logger.warning("No transaction to rollback")
                return True
            
            if self._current_transaction.rolled_back:
                logger.warning("Transaction already rolled back")
                return True
            
            try:
                # 運行回滾鉤子
                for hook in self._rollback_hooks:
                    try:
                        hook(self._current_transaction)
                    except Exception as e:
                        logger.error(f"Rollback hook failed: {e}")
                
                # 恢復備份文件
                self._restore_backups()
                
                # 重新加載配置到內存
                self._reload_configs_from_files()
                
                # 標記事務為已回滾
                self._current_transaction.rolled_back = True
                
                logger.info(f"Transaction rolled back: {self._current_transaction.transaction_id}")
                return True
                
            except Exception as e:
                logger.error(f"Error rolling back transaction: {e}")
                return False
    
    def _create_backups(self) -> None:
        """創建配置文件備份"""
        for operation in self._current_transaction.operations:
            file_path = operation['file_path']
            
            if os.path.exists(file_path):
                # 創建帶時間戳的備份文件名
                timestamp = int(time.time())
                backup_filename = f"{Path(file_path).stem}_{timestamp}{Path(file_path).suffix}"
                backup_path = self._backup_dir / backup_filename
                
                # 複製文件
                shutil.copy2(file_path, backup_path)
                self._current_transaction.add_backup(file_path, str(backup_path))
                
                logger.info(f"Backup created: {file_path} -> {backup_path}")
    
    def _restore_backups(self) -> None:
        """恢復備份文件"""
        for original_path, backup_path in self._current_transaction.backups.items():
            if os.path.exists(backup_path):
                shutil.copy2(backup_path, original_path)
                logger.info(f"Backup restored: {backup_path} -> {original_path}")
    
    def _write_config_file(self, config_type: ConfigType, file_path: str, data: Dict[str, Any]) -> None:
        """寫入配置文件"""
        if config_type == ConfigType.ENV_DATA:
            self._write_env_file(file_path, data)
        elif config_type == ConfigType.CONFIG_DATA:
            self._write_config_py_file(file_path, data)
        elif config_type == ConfigType.REMOTE_DATA:
            self._write_json_file(file_path, data)
        else:
            raise ValueError(f"Unknown config type: {config_type}")
    
    def _write_env_file(self, file_path: str, data: Dict[str, Any]) -> None:
        """寫入 .env 文件"""
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("# Wolf Chat Environment Configuration\n")
            f.write(f"# Generated by ConfigTransactionManager at {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            for key, value in data.items():
                if value is not None:
                    f.write(f"{key}={value}\n")
        
        logger.info(f"ENV file written: {file_path}")
    
    def _write_json_file(self, file_path: str, data: Dict[str, Any]) -> None:
        """寫入 JSON 文件"""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"JSON file written: {file_path}")
    
    def _write_config_py_file(self, file_path: str, data: Dict[str, Any]) -> None:
        """寫入 config.py 文件"""
        # 這個方法需要根據原始 Setup.py 中的 generate_config_file 邏輯來實現
        # 由於 config.py 生成邏輯較複雜，這裡提供一個簡化的佔位符
        
        # 首先檢查是否有模板文件
        template_path = "config_template.py"
        if os.path.exists(template_path):
            # 使用模板生成
            self._write_config_from_template(file_path, template_path, data)
        else:
            # 直接生成基本配置
            self._write_basic_config(file_path, data)
        
        logger.info(f"Config.py file written: {file_path}")
    
    def _write_config_from_template(self, file_path: str, template_path: str, data: Dict[str, Any]) -> None:
        """從模板生成 config.py"""
        # 這個方法需要實現模板替換邏輯
        # 暫時作為佔位符
        with open(template_path, 'r', encoding='utf-8') as template_file:
            template_content = template_file.read()
        
        # 執行模板替換
        # 實際實現時需要根據原始 Setup.py 的邏輯來替換
        processed_content = template_content  # 佔位符
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(processed_content)
    
    def _write_basic_config(self, file_path: str, data: Dict[str, Any]) -> None:
        """生成基本的 config.py"""
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("# Wolf Chat Configuration\n")
            f.write(f"# Generated by ConfigTransactionManager at {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            # 寫入基本配置項
            for key, value in data.items():
                if isinstance(value, str):
                    f.write(f'{key} = "{value}"\n')
                else:
                    f.write(f'{key} = {repr(value)}\n')
    
    def _reload_configs_from_files(self) -> None:
        """從文件重新加載配置到內存"""
        for config_type, file_path in self._config_file_paths.items():
            if os.path.exists(file_path):
                try:
                    if config_type == ConfigType.ENV_DATA:
                        data = self._load_env_file(file_path)
                    elif config_type == ConfigType.REMOTE_DATA:
                        data = self._load_json_file(file_path)
                    elif config_type == ConfigType.CONFIG_DATA:
                        data = self._load_config_py_file(file_path)
                    else:
                        continue
                    
                    self.state_manager.set_config_data(config_type, data)
                    self.state_manager.mark_config_clean(config_type)
                    
                except Exception as e:
                    logger.error(f"Error reloading config {config_type.value}: {e}")
    
    def _load_env_file(self, file_path: str) -> Dict[str, Any]:
        """加載 .env 文件"""
        data = {}
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        data[key.strip()] = value.strip()
        return data
    
    def _load_json_file(self, file_path: str) -> Dict[str, Any]:
        """加載 JSON 文件"""
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def _load_config_py_file(self, file_path: str) -> Dict[str, Any]:
        """加載 config.py 文件（簡化實現）"""
        # 這是一個簡化的實現，實際可能需要更複雜的解析
        return {}
    
    def _validate_config_dependencies(self) -> List[str]:
        """驗證配置間的依賴關係"""
        errors = []
        
        # 獲取所有配置數據
        env_data = self.state_manager.get_config_data(ConfigType.ENV_DATA)
        config_data = self.state_manager.get_config_data(ConfigType.CONFIG_DATA)
        remote_data = self.state_manager.get_config_data(ConfigType.REMOTE_DATA)
        
        # 檢查 API 密鑰依賴
        if config_data.get('use_openai', True):
            if not env_data.get('OPENAI_API_KEY'):
                errors.append("OpenAI API key is required when OpenAI is enabled")
        
        # 檢查 MCP 服務器依賴
        if config_data.get('exa_enabled', True):
            if not env_data.get('EXA_API_KEY'):
                errors.append("Exa API key is required when Exa MCP server is enabled")
        
        # 檢查遠端控制依賴
        if remote_data.get('enable_remote_control', False):
            if not remote_data.get('server_url'):
                errors.append("Server URL is required when remote control is enabled")
            if not remote_data.get('client_key'):
                errors.append("Client key is required when remote control is enabled")
        
        return errors
    
    def _cleanup_old_backups(self, keep_count: int = 10) -> None:
        """清理舊的備份文件"""
        try:
            backup_files = list(self._backup_dir.glob("*"))
            backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            for old_backup in backup_files[keep_count:]:
                old_backup.unlink()
                logger.info(f"Old backup cleaned up: {old_backup}")
                
        except Exception as e:
            logger.error(f"Error cleaning up old backups: {e}")
    
    # ================================================
    # 驗證器和鉤子管理
    # ================================================
    
    def add_validator(self, config_type: ConfigType, validator: Callable[[Dict[str, Any]], tuple[bool, List[str]]]) -> None:
        """添加配置驗證器"""
        self._validators[config_type] = validator
        logger.info(f"Validator added for {config_type.value}")
    
    def add_pre_commit_hook(self, hook: Callable[[ConfigTransaction], None]) -> None:
        """添加預提交鉤子"""
        self._pre_commit_hooks.append(hook)
        logger.info("Pre-commit hook added")
    
    def add_post_commit_hook(self, hook: Callable[[ConfigTransaction], None]) -> None:
        """添加後提交鉤子"""
        self._post_commit_hooks.append(hook)
        logger.info("Post-commit hook added")
    
    def add_rollback_hook(self, hook: Callable[[ConfigTransaction], None]) -> None:
        """添加回滾鉤子"""
        self._rollback_hooks.append(hook)
        logger.info("Rollback hook added")
    
    # ================================================
    # 便利方法
    # ================================================
    
    def atomic_config_update(self, updates: Dict[ConfigType, Dict[str, Any]]) -> bool:
        """原子性更新多個配置"""
        try:
            tx_id = self.begin_transaction()
            
            for config_type, data in updates.items():
                self.update_config(config_type, data)
            
            return self.commit_transaction()
            
        except Exception as e:
            logger.error(f"Atomic config update failed: {e}")
            try:
                self.rollback_transaction()
            except:
                pass
            return False
    
    def get_transaction_status(self) -> Optional[Dict[str, Any]]:
        """獲取當前事務狀態"""
        with self._transaction_lock:
            if not self._current_transaction:
                return None
            
            return {
                'transaction_id': self._current_transaction.transaction_id,
                'start_time': self._current_transaction.start_time,
                'operations_count': len(self._current_transaction.operations),
                'is_active': self._current_transaction.is_active(),
                'committed': self._current_transaction.committed,
                'rolled_back': self._current_transaction.rolled_back
            }

# 全局實例
config_transaction_manager = ConfigTransactionManager()
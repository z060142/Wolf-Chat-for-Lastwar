import os
import tkinter as tk
from tkinter import filedialog, messagebox
import json
import chromadb
import datetime
import time
import shutil
import pandas as pd
import threading
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.scrolled import ScrolledFrame
import zipfile
import logging
import sqlite3
import schedule
from typing import List, Dict, Any, Optional, Union, Tuple


class ChromaDBBackup:
    """ChromaDB備份處理程序 - 備份操作的主要數據模型"""
    
    def __init__(self):
        self.source_db_path = ""
        self.backup_dir = ""
        self.backups = []  # 所有備份的列表
        self.scheduled_jobs = {}  # 追蹤排程備份任務的字典
        self.is_running_backup = False
        self.current_backup_thread = None
        self.backup_history = []  # 追蹤成功和失敗的備份
        
        # 設置日誌
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler("chroma_backup.log", encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger("ChromaDBBackup")
    
    def set_source_db(self, db_path: str) -> bool:
        """設置源ChromaDB數據庫路徑"""
        if not os.path.exists(db_path):
            self.logger.error(f"源數據庫路徑不存在: {db_path}")
            return False
        
        # 檢查是否是有效的ChromaDB目錄
        if not self._is_valid_chroma_db(db_path):
            self.logger.error(f"不是有效的ChromaDB目錄: {db_path}")
            return False
        
        self.source_db_path = db_path
        self.logger.info(f"源數據庫設置為: {db_path}")
        return True
    
    def _is_valid_chroma_db(self, db_path: str) -> bool:
        """檢查目錄是否為有效的ChromaDB數據庫"""
        # 檢查關鍵ChromaDB文件
        sqlite_path = os.path.join(db_path, "chroma.sqlite3")
        return os.path.exists(sqlite_path)
    
    def set_backup_directory(self, directory_path: str) -> bool:
        """設置備份目錄並掃描現有備份"""
        if not os.path.exists(directory_path):
            try:
                os.makedirs(directory_path)
                self.logger.info(f"已創建備份目錄: {directory_path}")
            except Exception as e:
                self.logger.error(f"創建備份目錄失敗: {str(e)}")
                return False
        
        self.backup_dir = directory_path
        return self.scan_backups()
    
    def scan_backups(self) -> bool:
        """掃描備份目錄中的所有備份"""
        self.backups = []
        
        try:
            # 查找所有以chroma_backup_開頭的目錄
            for item in os.listdir(self.backup_dir):
                item_path = os.path.join(self.backup_dir, item)
                if os.path.isdir(item_path) and item.startswith("chroma_backup_"):
                    # 提取備份日期時間
                    try:
                        date_str = item.replace("chroma_backup_", "")
                        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d_%H-%M-%S")
                        
                        backup_info = {
                            "name": item,
                            "path": item_path,
                            "date": date_obj,
                            "formatted_date": date_obj.strftime("%Y-%m-%d %H:%M:%S"),
                            "size": self._get_dir_size(item_path)
                        }
                        
                        # 檢查是否是有效的ChromaDB目錄
                        if self._is_valid_chroma_db(item_path):
                            self.backups.append(backup_info)
                    except Exception as e:
                        self.logger.warning(f"無法解析備份 {item}: {str(e)}")
            
            # 按日期排序，最新的排在前面
            self.backups.sort(key=lambda x: x["date"], reverse=True)
            self.logger.info(f"找到 {len(self.backups)} 個備份")
            return True
            
        except Exception as e:
            self.logger.error(f"掃描備份時出錯: {str(e)}")
            return False
    
    def _get_dir_size(self, path: str) -> str:
        """獲取目錄大小並轉換為人類可讀格式"""
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if not os.path.islink(fp):
                    total_size += os.path.getsize(fp)
        
        # 將字節轉換為人類可讀格式
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if total_size < 1024.0:
                return f"{total_size:.2f} {unit}"
            total_size /= 1024.0
        
        return f"{total_size:.2f} PB"
    
    def create_backup(self, description: str = "") -> bool:
        """創建新的ChromaDB數據庫備份"""
        if not self.source_db_path or not self.backup_dir:
            self.logger.error("未設置源數據庫或備份目錄")
            return False
        
        if self.is_running_backup:
            self.logger.warning("備份操作已在進行中")
            return False
        
        self.is_running_backup = True
        
        try:
            # 使用時間戳創建備份名稱
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            backup_name = f"chroma_backup_{timestamp}"
            backup_path = os.path.join(self.backup_dir, backup_name)
            
            # 創建備份目錄
            os.makedirs(backup_path, exist_ok=True)
            
            # 創建包含備份信息的元數據文件
            metadata = {
                "source_db": self.source_db_path,
                "backup_time": timestamp,
                "description": description,
                "backup_type": "manual"
            }
            
            with open(os.path.join(backup_path, "backup_metadata.json"), "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=4)
            
            # 執行實際備份 - 複製SQLite數據庫
            source_db_file = os.path.join(self.source_db_path, "chroma.sqlite3")
            backup_db_file = os.path.join(backup_path, "chroma.sqlite3")
            
            # 使用SQLite備份API進行適當備份
            self._backup_sqlite_db(source_db_file, backup_db_file)
            
            # 複製ChromaDB目錄中的其他文件
            for item in os.listdir(self.source_db_path):
                source_item = os.path.join(self.source_db_path, item)
                if os.path.isfile(source_item) and item != "chroma.sqlite3":
                    shutil.copy2(source_item, os.path.join(backup_path, item))
            
            # 記錄成功的備份
            self.backup_history.append({
                "name": backup_name,
                "path": backup_path,
                "date": datetime.datetime.now(),
                "status": "success",
                "description": description
            })
            
            # 重新掃描備份以包含新備份
            self.scan_backups()
            
            self.logger.info(f"備份創建成功: {backup_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"創建備份時出錯: {str(e)}")
            # 記錄失敗的備份嘗試
            self.backup_history.append({
                "name": f"failed_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}",
                "date": datetime.datetime.now(),
                "status": "failed",
                "error": str(e),
                "description": description
            })
            return False
        finally:
            self.is_running_backup = False
    
    def _backup_sqlite_db(self, source_db: str, dest_db: str) -> None:
        """使用備份API正確備份SQLite數據庫"""
        try:
            # 連接源數據庫
            source_conn = sqlite3.connect(source_db)
            # 連接目標數據庫
            dest_conn = sqlite3.connect(dest_db)
            
            # 備份數據庫
            source_conn.backup(dest_conn)
            
            # 關閉連接
            source_conn.close()
            dest_conn.close()
            
            self.logger.info(f"SQLite數據庫備份成功: {source_db} -> {dest_db}")
        except Exception as e:
            self.logger.error(f"SQLite備份失敗: {str(e)}")
            raise
    
    def restore_backup(self, backup_index: int, restore_path: str = None) -> bool:
        """從備份還原"""
        if backup_index < 0 or backup_index >= len(self.backups):
            self.logger.error(f"無效的備份索引: {backup_index}")
            return False
        
        if self.is_running_backup:
            self.logger.warning("備份操作正在進行中，無法執行還原")
            return False
        
        self.is_running_backup = True
        
        try:
            backup = self.backups[backup_index]
            backup_path = backup["path"]
            
            # 如果沒有指定還原路徑，則使用源數據庫路徑
            if not restore_path:
                restore_path = self.source_db_path
            
            # 確保還原目錄存在
            os.makedirs(restore_path, exist_ok=True)
            
            # 備份當前數據庫作為安全措施
            current_time = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            safety_backup_path = os.path.join(
                os.path.dirname(restore_path),
                f"pre_restore_backup_{current_time}"
            )
            
            # 只有在還原到現有路徑時才創建安全備份
            if os.path.exists(os.path.join(restore_path, "chroma.sqlite3")):
                os.makedirs(safety_backup_path, exist_ok=True)
                self.logger.info(f"創建還原前的安全備份: {safety_backup_path}")
                
                # 複製現有數據庫文件到安全備份
                source_db_file = os.path.join(restore_path, "chroma.sqlite3")
                safety_db_file = os.path.join(safety_backup_path, "chroma.sqlite3")
                
                # 使用sqlite備份API
                self._backup_sqlite_db(source_db_file, safety_db_file)
                
                # 複製其他文件
                for item in os.listdir(restore_path):
                    source_item = os.path.join(restore_path, item)
                    if os.path.isfile(source_item) and item != "chroma.sqlite3":
                        shutil.copy2(source_item, os.path.join(safety_backup_path, item))
            
            # 從備份還原數據庫
            backup_db_file = os.path.join(backup_path, "chroma.sqlite3")
            restore_db_file = os.path.join(restore_path, "chroma.sqlite3")
            
            # 確保目標目錄中沒有鎖定的數據庫文件
            if os.path.exists(restore_db_file):
                os.remove(restore_db_file)
            
            # 使用sqlite備份API還原
            self._backup_sqlite_db(backup_db_file, restore_db_file)
            
            # 複製其他文件
            for item in os.listdir(backup_path):
                source_item = os.path.join(backup_path, item)
                if os.path.isfile(source_item) and item != "chroma.sqlite3" and item != "backup_metadata.json":
                    shutil.copy2(source_item, os.path.join(restore_path, item))
            
            self.logger.info(f"備份還原成功: {backup['name']} -> {restore_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"還原備份時出錯: {str(e)}")
            return False
        finally:
            self.is_running_backup = False
    
    def delete_backup(self, backup_index: int) -> bool:
        """刪除指定的備份"""
        if backup_index < 0 or backup_index >= len(self.backups):
            self.logger.error(f"無效的備份索引: {backup_index}")
            return False
        
        try:
            backup = self.backups[backup_index]
            backup_path = backup["path"]
            
            # 刪除備份目錄
            shutil.rmtree(backup_path)
            
            # 從列表中移除備份
            self.backups.pop(backup_index)
            
            self.logger.info(f"已刪除備份: {backup['name']}")
            return True
            
        except Exception as e:
            self.logger.error(f"刪除備份時出錯: {str(e)}")
            return False
    
    def export_backup(self, backup_index: int, export_path: str) -> bool:
        """將備份導出為壓縮文件"""
        if backup_index < 0 or backup_index >= len(self.backups):
            self.logger.error(f"無效的備份索引: {backup_index}")
            return False
        
        try:
            backup = self.backups[backup_index]
            backup_path = backup["path"]
            
            # 創建ZIP文件
            with zipfile.ZipFile(export_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # 遍歷備份目錄中的所有文件
                for root, dirs, files in os.walk(backup_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        # 計算相對路徑，以便在ZIP中保持目錄結構
                        rel_path = os.path.relpath(file_path, os.path.dirname(backup_path))
                        zipf.write(file_path, rel_path)
            
            self.logger.info(f"備份已導出到: {export_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"導出備份時出錯: {str(e)}")
            return False
    
    def import_backup(self, zip_path: str) -> bool:
        """從ZIP文件導入備份"""
        if not os.path.exists(zip_path) or not zipfile.is_zipfile(zip_path):
            self.logger.error(f"無效的ZIP文件: {zip_path}")
            return False
        
        try:
            # 創建臨時目錄
            temp_dir = os.path.join(self.backup_dir, f"temp_import_{int(time.time())}")
            os.makedirs(temp_dir, exist_ok=True)
            
            # 解壓ZIP文件
            with zipfile.ZipFile(zip_path, 'r') as zipf:
                zipf.extractall(temp_dir)
            
            # 檢查解壓的文件是否是有效的ChromaDB備份
            if not self._is_valid_chroma_db(temp_dir):
                # 檢查子目錄
                for item in os.listdir(temp_dir):
                    item_path = os.path.join(temp_dir, item)
                    if os.path.isdir(item_path) and self._is_valid_chroma_db(item_path):
                        # 找到有效的子目錄
                        temp_dir = item_path
                        break
                else:
                    # 沒有找到有效的備份
                    shutil.rmtree(temp_dir)
                    self.logger.error(f"ZIP文件不包含有效的ChromaDB備份")
                    return False
            
            # 創建新的備份目錄
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            backup_name = f"chroma_backup_{timestamp}_imported"
            backup_path = os.path.join(self.backup_dir, backup_name)
            
            # 移動文件到新的備份目錄
            shutil.move(temp_dir, backup_path)
            
            # 添加元數據
            metadata = {
                "source": zip_path,
                "import_time": timestamp,
                "description": f"從 {os.path.basename(zip_path)} 導入",
                "backup_type": "imported"
            }
            
            with open(os.path.join(backup_path, "backup_metadata.json"), "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=4)
            
            # 重新掃描備份
            self.scan_backups()
            
            self.logger.info(f"從 {zip_path} 導入備份成功")
            return True
            
        except Exception as e:
            self.logger.error(f"導入備份時出錯: {str(e)}")
            # 清理臨時目錄
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            return False
    
    def schedule_backup(self, interval: str, description: str = "", keep_count: int = 0, at_time: Optional[str] = None) -> bool:
        """排程定期備份
        
        interval: 備份間隔 - daily, weekly, hourly
        description: 備份描述
        keep_count: 保留的備份數量，0表示不限制
        at_time: 執行的時間，格式 "HH:MM" (例如 "14:30")，僅對 daily, weekly, monthly 有效
        """
        job_id = f"scheduled_{interval}_{int(time.time())}"
        
        # 驗證 at_time 格式
        if at_time:
            try:
                time.strptime(at_time, "%H:%M")
            except ValueError:
                self.logger.error(f"無效的時間格式: {at_time}. 請使用 HH:MM 格式.")
                return False
        
        # 如果是每小時備份，則忽略 at_time
        if interval == "hourly":
            at_time = None 
            
        try:
            # 根據間隔設置排程
            if interval == "hourly":
                schedule.every().hour.do(self._run_scheduled_backup, job_id=job_id, description=description, interval=interval, at_time=at_time)
            elif interval == "daily":
                schedule_time = at_time if at_time else "00:00"
                schedule.every().day.at(schedule_time).do(self._run_scheduled_backup, job_id=job_id, description=description, interval=interval, at_time=at_time)
            elif interval == "weekly":
                schedule_time = at_time if at_time else "00:00"
                schedule.every().monday.at(schedule_time).do(self._run_scheduled_backup, job_id=job_id, description=description, interval=interval, at_time=at_time)
            elif interval == "monthly":
                schedule_time = at_time if at_time else "00:00"
                # 每月1日執行
                schedule.every().day.at(schedule_time).do(self._check_monthly_schedule, job_id=job_id, description=description, interval=interval, at_time=at_time)
            else:
                self.logger.warning(f"不支援的排程間隔: {interval}，改用每日排程")
                schedule_time = at_time if at_time else "00:00"
                schedule.every().day.at(schedule_time).do(self._run_scheduled_backup, job_id=job_id, description=description, interval="daily", at_time=at_time)
            
            # 存儲排程任務信息
            self.scheduled_jobs[job_id] = {
                "interval": interval,
                "description": description,
                "created": datetime.datetime.now(),
                "keep_count": keep_count,
                "at_time": at_time, # 新增
                "next_run": self._get_next_run_time(interval, at_time)
            }
            
            self.logger.info(f"已排程 {interval} 備份 (時間: {at_time if at_time else '預設'})，任務ID: {job_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"設置排程備份時出錯: {str(e)}")
            return False
    
    def _check_monthly_schedule(self, job_id, description, interval):
        """檢查是否應運行月度備份"""
        if datetime.datetime.now().day == 1:
            return self._run_scheduled_backup(job_id, description, interval)
        return None
    
    def _get_next_run_time(self, interval: str, at_time: Optional[str] = None) -> datetime.datetime:
        """獲取下次執行時間"""
        now = datetime.datetime.now()
        
        target_hour, target_minute = 0, 0
        if at_time:
            try:
                t = time.strptime(at_time, "%H:%M")
                target_hour, target_minute = t.tm_hour, t.tm_min
            except ValueError:
                # 如果格式錯誤，使用預設時間
                pass

        if interval == "hourly":
            # 每小時任務，忽略 at_time，在下一個整點執行
            next_run_time = now.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)
            # 如果計算出的時間已過，則再加一小時
            if next_run_time <= now:
                 next_run_time += datetime.timedelta(hours=1)
            return next_run_time
        
        elif interval == "daily":
            next_run_time = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
            if next_run_time <= now: # 如果今天的時間已過，則設為明天
                next_run_time += datetime.timedelta(days=1)
            return next_run_time
            
        elif interval == "weekly":
            # 計算下個星期一
            next_run_time = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
            days_ahead = 0 - next_run_time.weekday() # 0 is Monday
            if days_ahead <= 0: # Target day already happened this week
                days_ahead += 7
            next_run_time += datetime.timedelta(days=days_ahead)
            # 如果計算出的時間已過 (例如今天是星期一，但設定的時間已過)，則設為下下星期一
            if next_run_time <= now:
                 next_run_time += datetime.timedelta(weeks=1)
            return next_run_time
            
        elif interval == "monthly":
            # 計算下個月1日
            next_run_time = now.replace(day=1, hour=target_hour, minute=target_minute, second=0, microsecond=0)
            if now.month == 12:
                next_run_time = next_run_time.replace(year=now.year + 1, month=1)
            else:
                next_run_time = next_run_time.replace(month=now.month + 1)
            
            # 如果計算出的時間已過 (例如今天是1號，但設定的時間已過)，則設為下下個月1號
            if next_run_time <= now:
                if next_run_time.month == 12:
                    next_run_time = next_run_time.replace(year=next_run_time.year + 1, month=1)
                else:
                    next_run_time = next_run_time.replace(month=next_run_time.month + 1)
            return next_run_time
        
        # 默認返回明天
        default_next_run = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0) + datetime.timedelta(days=1)
        return default_next_run

    def _run_scheduled_backup(self, job_id: str, description: str, interval: str, at_time: Optional[str] = None):
        """執行排程備份任務"""
        job_info = self.scheduled_jobs.get(job_id)
        if not job_info:
            self.logger.warning(f"找不到排程任務: {job_id}")
            return None
        
        try:
            # 更新下次執行時間
            self.scheduled_jobs[job_id]["next_run"] = self._get_next_run_time(interval, at_time)
            
            # 執行備份
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            backup_desc = f"{description} (排程 {interval})"
            
            # 設置備份類型
            backup_name = f"chroma_backup_{timestamp}"
            backup_path = os.path.join(self.backup_dir, backup_name)
            
            # 創建備份目錄
            os.makedirs(backup_path, exist_ok=True)
            
            # 創建包含備份信息的元數據文件
            metadata = {
                "source_db": self.source_db_path,
                "backup_time": timestamp,
                "description": backup_desc,
                "backup_type": "scheduled",
                "schedule_info": {
                    "job_id": job_id,
                    "interval": interval
                }
            }
            
            with open(os.path.join(backup_path, "backup_metadata.json"), "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=4)
            
            # 執行實際備份
            source_db_file = os.path.join(self.source_db_path, "chroma.sqlite3")
            backup_db_file = os.path.join(backup_path, "chroma.sqlite3")
            
            # 使用SQLite備份API
            self._backup_sqlite_db(source_db_file, backup_db_file)
            
            # 複製其他文件
            for item in os.listdir(self.source_db_path):
                source_item = os.path.join(self.source_db_path, item)
                if os.path.isfile(source_item) and item != "chroma.sqlite3":
                    shutil.copy2(source_item, os.path.join(backup_path, item))
            
            # 更新成功的備份
            self.backup_history.append({
                "name": backup_name,
                "path": backup_path,
                "date": datetime.datetime.now(),
                "status": "success",
                "description": backup_desc,
                "scheduled": True,
                "job_id": job_id
            })
            
            # 重新掃描備份
            self.scan_backups()
            
            # 保留限制處理
            if job_info["keep_count"] > 0:
                self._cleanup_scheduled_backups(job_id, job_info["keep_count"])
            
            self.logger.info(f"排程備份 {job_id} 完成: {backup_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"執行排程備份時出錯: {str(e)}")
            # 記錄失敗的備份
            self.backup_history.append({
                "name": f"failed_scheduled_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}",
                "date": datetime.datetime.now(),
                "status": "failed",
                "error": str(e),
                "description": description,
                "scheduled": True,
                "job_id": job_id
            })
            return False
    
    def _cleanup_scheduled_backups(self, job_id, keep_count):
        """根據保留數量清理舊的排程備份"""
        # 獲取與該排程關聯的所有備份
        job_backups = []
        for i, backup in enumerate(self.backups):
            # 檢查元數據文件
            metadata_path = os.path.join(backup["path"], "backup_metadata.json")
            if os.path.exists(metadata_path):
                try:
                    with open(metadata_path, "r", encoding="utf-8") as f:
                        metadata = json.load(f)
                    
                    if metadata.get("backup_type") == "scheduled" and \
                       metadata.get("schedule_info", {}).get("job_id") == job_id:
                        job_backups.append((i, backup))
                except Exception:
                    pass
        
        # 按日期排序
        job_backups.sort(key=lambda x: x[1]["date"], reverse=True)
        
        # 刪除超出保留數量的舊備份
        if len(job_backups) > keep_count:
            for index, _ in job_backups[keep_count:]:
                self.delete_backup(index)
    
    def cancel_scheduled_backup(self, job_id: str) -> bool:
        """取消排程備份任務"""
        if job_id not in self.scheduled_jobs:
            self.logger.error(f"找不到排程任務: {job_id}")
            return False
        
        try:
            # 從schedule中移除任務
            schedule.clear(job_id)
            
            # 從字典中移除
            self.scheduled_jobs.pop(job_id)
            
            self.logger.info(f"已取消排程備份任務: {job_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"取消排程備份時出錯: {str(e)}")
            return False
    
    def get_db_info(self) -> Dict:
        """獲取數據庫信息"""
        if not self.source_db_path or not os.path.exists(self.source_db_path):
            return {"status": "未設置有效的數據庫路徑"}
        
        try:
            # 連接到數據庫
            conn = sqlite3.connect(os.path.join(self.source_db_path, "chroma.sqlite3"))
            cursor = conn.cursor()
            
            # 獲取數據庫大小
            db_size = os.path.getsize(os.path.join(self.source_db_path, "chroma.sqlite3"))
            
            # 獲取表列表
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            
            # 獲取每個表的行數
            table_counts = {}
            for table in tables:
                table_name = table[0]
                cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
                count = cursor.fetchone()[0]
                table_counts[table_name] = count
            
            # 獲取 embeddings 數量 (如果存在這樣的表)
            embeddings_count = 0
            if "embeddings" in table_counts:
                embeddings_count = table_counts["embeddings"]
            
            # 獲取最後修改時間
            last_modified = datetime.datetime.fromtimestamp(
                os.path.getmtime(os.path.join(self.source_db_path, "chroma.sqlite3"))
            )
            
            # 獲取數據庫版本
            cursor.execute("PRAGMA user_version;")
            db_version = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                "status": "ok",
                "path": self.source_db_path,
                "size": self._format_size(db_size),
                "tables": table_counts,
                "embeddings_count": embeddings_count,
                "last_modified": last_modified.strftime("%Y-%m-%d %H:%M:%S"),
                "db_version": db_version
            }
            
        except Exception as e:
            self.logger.error(f"獲取數據庫信息時出錯: {str(e)}")
            return {
                "status": "error",
                "error": str(e),
                "path": self.source_db_path
            }
    
    def _format_size(self, size_bytes):
        """格式化文件大小為人類可讀格式"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"
    
    def get_scheduled_jobs_info(self) -> List[Dict]:
        """獲取所有排程任務的信息"""
        jobs_info = []
        
        for job_id, job_data in self.scheduled_jobs.items():
            job_info = {
                "id": job_id,
                "interval": job_data["interval"],
                "description": job_data["description"],
                "created": job_data["created"].strftime("%Y-%m-%d %H:%M:%S"),
                "next_run": job_data["next_run"].strftime("%Y-%m-%d %H:%M:%S") if job_data["next_run"] else "未知",
                "keep_count": job_data["keep_count"],
                "at_time": job_data.get("at_time", "N/A") # 新增
            }
            jobs_info.append(job_info)
        
        return jobs_info
    
    def run_scheduler(self):
        """運行排程器，處理所有待執行的排程任務"""
        schedule.run_pending()


class ChromaDBBackupUI:
    """ChromaDB備份工具的使用者界面"""
    
    def __init__(self, root):
        self.root = root
        self.backup = ChromaDBBackup()
        
        # 設置視窗
        self.root.title("ChromaDB 備份工具")
        self.root.geometry("1280x800")
        self.setup_ui()
        
        # 默認主題
        self.current_theme = "darkly"  # ttkbootstrap的深色主題
        
        # 儲存配置
        self.config_path = os.path.join(str(Path.home()), ".chroma_backup_config.json")
        self.config = self.load_config()
        
        # 應用保存的配置
        if self.config.get("last_source_db"):
            self.source_db_var.set(self.config["last_source_db"])
        
        if self.config.get("last_backup_dir"):
            self.backup_dir_var.set(self.config["last_backup_dir"])
            self.load_directories()
        
        # 設置排程器執行器
        self.scheduler_running = True
        self.scheduler_thread = threading.Thread(target=self.run_scheduler, daemon=True)
        self.scheduler_thread.start()
    
    def setup_ui(self):
        """設置使用者界面"""
        # 創建主佈局
        self.main_frame = ttk.Frame(self.root, padding=10)
        self.main_frame.pack(fill=BOTH, expand=YES)
        
        # 頂部面板（源數據庫和備份目錄設置）
        self.top_panel = ttk.Frame(self.main_frame)
        self.top_panel.pack(fill=X, pady=(0, 10))
        
        # 左側面板（備份列表和操作）
        self.left_panel = ttk.Frame(self.main_frame, width=400)
        self.left_panel.pack(side=LEFT, fill=BOTH, expand=YES, padx=(0, 5))
        
        # 右側面板（排程和統計）
        self.right_panel = ttk.Frame(self.main_frame, width=300)
        self.right_panel.pack(side=LEFT, fill=BOTH, padx=(5, 0))
        
        # 設置頂部面板
        self.setup_directory_frame()
        
        # 設置左側面板
        self.setup_backups_frame()
        
        # 設置右側面板
        self.setup_schedule_frame()
        self.setup_stats_frame()
        
        # 設置狀態欄
        self.setup_status_bar()
        
        # 設置菜單
        self.setup_menu()
    
    def setup_menu(self):
        """設置選單列"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # 檔案選單
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="檔案", menu=file_menu)
        file_menu.add_command(label="選擇源數據庫...", command=self.browse_source_db)
        file_menu.add_command(label="選擇備份目錄...", command=self.browse_backup_dir)
        file_menu.add_separator()
        file_menu.add_command(label="導入備份...", command=self.import_backup_dialog)
        file_menu.add_command(label="導出備份...", command=self.export_backup_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="離開", command=self.root.quit)
        
        # 備份選單
        backup_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="備份", menu=backup_menu)
        backup_menu.add_command(label="創建新備份", command=self.create_backup_dialog)
        backup_menu.add_command(label="還原備份...", command=self.restore_backup_dialog)
        backup_menu.add_command(label="刪除備份...", command=self.delete_backup_dialog)
        backup_menu.add_separator()
        backup_menu.add_command(label="排程備份...", command=self.schedule_backup_dialog)
        backup_menu.add_command(label="查看排程任務", command=self.view_scheduled_jobs)
        
        # 工具選單
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="工具", menu=tools_menu)
        tools_menu.add_command(label="備份歷史", command=self.view_backup_history)
        tools_menu.add_command(label="數據庫資訊", command=self.view_db_info)
        tools_menu.add_separator()
        tools_menu.add_command(label="打開備份閱讀器", command=self.open_backup_reader)
        
        # 檢視選單
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="檢視", menu=view_menu)
        view_menu.add_command(label="切換深色/淺色主題", command=self.toggle_theme)
        view_menu.add_command(label="刷新", command=self.refresh_ui)
        
        # 說明選單
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="說明", menu=help_menu)
        help_menu.add_command(label="關於", command=self.show_about)
        help_menu.add_command(label="查看日誌", command=self.open_log_file)
    
    def setup_directory_frame(self):
        """設置目錄選擇框架"""
        dir_frame = ttk.Frame(self.top_panel)
        dir_frame.pack(fill=X)
        
        # 源數據庫選擇
        source_frame = ttk.LabelFrame(dir_frame, text="源數據庫", padding=10)
        source_frame.pack(side=LEFT, fill=X, expand=YES, padx=(0, 5))
        
        self.source_db_var = tk.StringVar()
        
        ttk.Entry(source_frame, textvariable=self.source_db_var).pack(side=LEFT, fill=X, expand=YES)
        ttk.Button(source_frame, text="瀏覽", command=self.browse_source_db).pack(side=LEFT, padx=(5, 0))
        
        # 備份目錄選擇
        backup_frame = ttk.LabelFrame(dir_frame, text="備份目錄", padding=10)
        backup_frame.pack(side=LEFT, fill=X, expand=YES, padx=(5, 0))
        
        self.backup_dir_var = tk.StringVar()
        
        ttk.Entry(backup_frame, textvariable=self.backup_dir_var).pack(side=LEFT, fill=X, expand=YES)
        ttk.Button(backup_frame, text="瀏覽", command=self.browse_backup_dir).pack(side=LEFT, padx=(5, 0))
        
        # 載入按鈕
        load_frame = ttk.Frame(self.top_panel)
        load_frame.pack(fill=X, pady=5)
        
        ttk.Button(
            load_frame,
            text="載入目錄",
            command=self.load_directories,
            style="Accent.TButton"
        ).pack(side=RIGHT)
        
        # 備份按鈕
        ttk.Button(
            load_frame,
            text="創建新備份",
            command=self.create_backup_dialog,
            style="success.TButton"
        ).pack(side=RIGHT, padx=5)
    
    def setup_backups_frame(self):
        """設置備份列表框架"""
        backups_frame = ttk.LabelFrame(self.left_panel, text="備份列表", padding=10)
        backups_frame.pack(fill=BOTH, expand=YES)
        
        # 工具欄
        toolbar = ttk.Frame(backups_frame)
        toolbar.pack(fill=X, pady=(0, 5))
        
        # 搜索欄
        self.backup_search_var = tk.StringVar()
        self.backup_search_var.trace("w", self.filter_backups)
        
        ttk.Label(toolbar, text="搜索:").pack(side=LEFT)
        ttk.Entry(toolbar, textvariable=self.backup_search_var).pack(side=LEFT, fill=X, expand=YES)
        
        ttk.Button(toolbar, text="刷新", command=self.refresh_backups).pack(side=RIGHT, padx=5)
        
        # 備份列表
        list_frame = ttk.Frame(backups_frame)
        list_frame.pack(fill=BOTH, expand=YES)
        
        columns = ("name", "date", "size")
        self.backups_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=15)
        self.backups_tree.heading("name", text="名稱")
        self.backups_tree.heading("date", text="日期")
        self.backups_tree.heading("size", text="大小")
        self.backups_tree.column("name", width=250)
        self.backups_tree.column("date", width=150)
        self.backups_tree.column("size", width=100)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=VERTICAL, command=self.backups_tree.yview)
        self.backups_tree.configure(yscrollcommand=scrollbar.set)
        
        self.backups_tree.pack(side=LEFT, fill=BOTH, expand=YES)
        scrollbar.pack(side=RIGHT, fill=Y)
        
        # 雙擊查看詳情
        self.backups_tree.bind("<Double-1>", self.view_backup_details)
        
        # 右鍵選單
        self.backup_context_menu = tk.Menu(self.backups_tree, tearoff=0)
        self.backup_context_menu.add_command(label="查看詳情", command=self.view_backup_details_from_menu)
        self.backup_context_menu.add_command(label="還原此備份", command=self.restore_selected_backup)
        self.backup_context_menu.add_command(label="導出備份", command=self.export_selected_backup)
        self.backup_context_menu.add_separator()
        self.backup_context_menu.add_command(label="刪除備份", command=self.delete_selected_backup)
        
        self.backups_tree.bind("<Button-3>", self.show_backup_context_menu)
        
        # 操作按鈕
        action_frame = ttk.Frame(backups_frame)
        action_frame.pack(fill=X, pady=(5, 0))
        
        ttk.Button(
            action_frame,
            text="還原",
            command=self.restore_selected_backup,
            style="info.TButton"
        ).pack(side=LEFT, padx=(0, 5))
        
        ttk.Button(
            action_frame,
            text="刪除",
            command=self.delete_selected_backup,
            style="danger.TButton"
        ).pack(side=LEFT)
        
        ttk.Button(
            action_frame,
            text="導出",
            command=self.export_selected_backup
        ).pack(side=LEFT, padx=(5, 0))
    
    def setup_schedule_frame(self):
        """設置排程框架"""
        schedule_frame = ttk.LabelFrame(self.right_panel, text="排程備份", padding=10)
        schedule_frame.pack(fill=X, pady=(0, 10))
        
        # 快速排程按鈕
        quick_frame = ttk.Frame(schedule_frame)
        quick_frame.pack(fill=X, pady=(0, 10))
        
        ttk.Label(quick_frame, text="快速排程:").pack(side=LEFT)
        
        ttk.Button(
            quick_frame,
            text="每小時",
            command=lambda: self.quick_schedule("hourly")
        ).pack(side=LEFT, padx=5)
        
        ttk.Button(
            quick_frame,
            text="每日",
            command=lambda: self.quick_schedule("daily")
        ).pack(side=LEFT, padx=5)
        
        ttk.Button(
            quick_frame,
            text="每週",
            command=lambda: self.quick_schedule("weekly")
        ).pack(side=LEFT, padx=5)
        
        # 排程任務列表
        ttk.Label(schedule_frame, text="排程任務:").pack(anchor=W)
        
        jobs_frame = ttk.Frame(schedule_frame)
        jobs_frame.pack(fill=BOTH, expand=YES)
        
        columns = ("interval", "next_run", "at_time") # 新增 at_time
        self.jobs_tree = ttk.Treeview(jobs_frame, columns=columns, show="headings", height=5)
        self.jobs_tree.heading("interval", text="間隔")
        self.jobs_tree.heading("next_run", text="下次執行")
        self.jobs_tree.heading("at_time", text="執行時間") # 新增
        self.jobs_tree.column("interval", width=100)
        self.jobs_tree.column("next_run", width=150)
        self.jobs_tree.column("at_time", width=80) # 新增
        
        scrollbar = ttk.Scrollbar(jobs_frame, orient=VERTICAL, command=self.jobs_tree.yview)
        self.jobs_tree.configure(yscrollcommand=scrollbar.set)
        
        self.jobs_tree.pack(side=LEFT, fill=BOTH, expand=YES)
        scrollbar.pack(side=RIGHT, fill=Y)
        
        # 排程操作按鈕
        actions_frame = ttk.Frame(schedule_frame)
        actions_frame.pack(fill=X, pady=(5, 0))
        
        ttk.Button(
            actions_frame,
            text="創建排程",
            command=self.schedule_backup_dialog
        ).pack(side=LEFT, padx=(0, 5))
        
        ttk.Button(
            actions_frame,
            text="取消排程",
            command=self.cancel_selected_job,
            style="warning.TButton"
        ).pack(side=LEFT)
        
        ttk.Button(
            actions_frame,
            text="立即執行",
            command=self.run_selected_job
        ).pack(side=RIGHT)
    
    def setup_stats_frame(self):
        """設置統計信息框架"""
        stats_frame = ttk.LabelFrame(self.right_panel, text="統計與資訊", padding=10)
        stats_frame.pack(fill=BOTH, expand=YES)
        
        # 數據庫信息
        db_frame = ttk.Frame(stats_frame)
        db_frame.pack(fill=X, pady=(0, 10))
        
        ttk.Label(db_frame, text="數據庫概況", font=("TkDefaultFont", 10, "bold")).pack(anchor=W)
        
        self.db_info_var = tk.StringVar(value="未載入數據庫")
        ttk.Label(db_frame, textvariable=self.db_info_var, wraplength=250).pack(anchor=W, pady=5)
        
        ttk.Button(
            db_frame,
            text="查看詳情",
            command=self.view_db_info
        ).pack(anchor=W)
        
        # 備份統計
        backup_stats_frame = ttk.Frame(stats_frame)
        backup_stats_frame.pack(fill=X, pady=10)
        
        ttk.Label(backup_stats_frame, text="備份統計", font=("TkDefaultFont", 10, "bold")).pack(anchor=W)
        
        self.backup_stats_var = tk.StringVar(value="未載入備份")
        ttk.Label(backup_stats_frame, textvariable=self.backup_stats_var, wraplength=250).pack(anchor=W, pady=5)
        
        # 圖表區域
        chart_frame = ttk.Frame(stats_frame)
        chart_frame.pack(fill=BOTH, expand=YES)
        
        self.chart_container = ttk.Frame(chart_frame)
        self.chart_container.pack(fill=BOTH, expand=YES)
        
        ttk.Button(
            stats_frame,
            text="查看備份歷史",
            command=self.view_backup_history
        ).pack(anchor=W, pady=(10, 0))
    
    def setup_status_bar(self):
        """設置狀態欄"""
        status_frame = ttk.Frame(self.root)
        status_frame.pack(side=BOTTOM, fill=X)
        
        self.status_var = tk.StringVar(value="就緒")
        status_label = ttk.Label(status_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=W)
        status_label.pack(fill=X)
    
    def browse_source_db(self):
        """瀏覽選擇源數據庫目錄"""
        directory = filedialog.askdirectory(
            title="選擇ChromaDB源數據庫目錄",
            initialdir=self.source_db_var.get() or str(Path.home())
        )
        
        if directory:
            self.source_db_var.set(directory)
    
    def browse_backup_dir(self):
        """瀏覽選擇備份目錄"""
        directory = filedialog.askdirectory(
            title="選擇ChromaDB備份目錄",
            initialdir=self.backup_dir_var.get() or str(Path.home())
        )
        
        if directory:
            self.backup_dir_var.set(directory)
    
    def load_directories(self):
        """載入源數據庫和備份目錄"""
        source_db = self.source_db_var.get()
        backup_dir = self.backup_dir_var.get()
        
        if not source_db or not backup_dir:
            messagebox.showwarning("警告", "請同時指定源數據庫和備份目錄")
            return
        
        self.status_var.set("正在驗證目錄...")
        self.root.update_idletasks()
        
        # 驗證源數據庫
        if not self.backup.set_source_db(source_db):
            messagebox.showerror("錯誤", f"無效的ChromaDB源數據庫目錄: {source_db}")
            self.status_var.set("載入失敗")
            return
        
        # 設置備份目錄
        if not self.backup.set_backup_directory(backup_dir):
            messagebox.showerror("錯誤", f"無法設置備份目錄: {backup_dir}")
            self.status_var.set("載入失敗")
            return
        
        # 保存配置
        self.config["last_source_db"] = source_db
        self.config["last_backup_dir"] = backup_dir
        self.save_config()
        
        # 更新UI
        self.refresh_ui()
        self.status_var.set("目錄已載入")
    
    def refresh_ui(self):
        """刷新整個UI"""
        self.refresh_backups()
        self.refresh_scheduled_jobs()
        self.update_stats()
        self.update_chart()
    
    def refresh_backups(self):
        """刷新備份列表"""
        self.status_var.set("正在刷新備份列表...")
        self.root.update_idletasks()
        
        # 重新掃描備份
        self.backup.scan_backups()
        
        # 清空現有列表
        for item in self.backups_tree.get_children():
            self.backups_tree.delete(item)
        
        # 添加備份
        for backup in self.backup.backups:
            self.backups_tree.insert(
                "", "end",
                values=(backup["name"], backup["formatted_date"], backup["size"])
            )
        
        self.status_var.set(f"已找到 {len(self.backup.backups)} 個備份")
    
    def filter_backups(self, *args):
        """根據搜索條件過濾備份列表"""
        search_text = self.backup_search_var.get().lower()
        
        # 清空列表
        for item in self.backups_tree.get_children():
            self.backups_tree.delete(item)
        
        # 添加匹配的備份
        for backup in self.backup.backups:
            if search_text in backup["name"].lower() or search_text in backup["formatted_date"].lower():
                self.backups_tree.insert(
                    "", "end",
                    values=(backup["name"], backup["formatted_date"], backup["size"])
                )
    
    def refresh_scheduled_jobs(self):
        """刷新排程任務列表"""
        # 清空現有列表
        for item in self.jobs_tree.get_children():
            self.jobs_tree.delete(item)
        
        # 添加排程任務
        for job in self.backup.get_scheduled_jobs_info():
            self.jobs_tree.insert(
                "", "end",
                iid=job["id"],  # 使用任務ID作為樹項目ID
                values=(
                    f"{job['interval']} ({job['description']})",
                    job["next_run"],
                    job.get("at_time", "N/A") # 新增
                )
            )
    
    def update_stats(self):
        """更新統計信息"""
        # 更新數據庫信息
        db_info = self.backup.get_db_info()
        
        if db_info["status"] == "ok":
            info_text = f"路徑: {os.path.basename(db_info['path'])}\n"
            info_text += f"大小: {db_info['size']}\n"
            info_text += f"嵌入向量: {db_info['embeddings_count']}\n"
            info_text += f"最後修改: {db_info['last_modified']}"
            
            self.db_info_var.set(info_text)
        else:
            self.db_info_var.set(f"錯誤: {db_info.get('error', '未知錯誤')}")
        
        # 更新備份統計
        if self.backup.backups:
            # 計算總備份大小
            total_size = sum([os.path.getsize(os.path.join(backup["path"], "chroma.sqlite3")) 
                             for backup in self.backup.backups 
                             if os.path.exists(os.path.join(backup["path"], "chroma.sqlite3"))])
            
            # 計算最新與最舊備份的日期差
            if len(self.backup.backups) >= 2:
                newest = self.backup.backups[0]["date"]
                oldest = self.backup.backups[-1]["date"]
                date_range = (newest - oldest).days
            else:
                date_range = 0
            
            stats_text = f"備份總數: {len(self.backup.backups)}\n"
            stats_text += f"總大小: {self.backup._format_size(total_size)}\n"
            stats_text += f"日期範圍: {date_range} 天\n"
            
            # 計算每月備份數量
            if len(self.backup.backups) > 0:
                this_month = datetime.datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                month_count = len([b for b in self.backup.backups if b["date"] >= this_month])
                stats_text += f"本月備份: {month_count} 個"
            
            self.backup_stats_var.set(stats_text)
        else:
            self.backup_stats_var.set("尚無備份")
    
    def update_chart(self):
        """更新圖表"""
        # 清空圖表容器
        for widget in self.chart_container.winfo_children():
            widget.destroy()
        
        if not self.backup.backups:
            return
        
        # 準備數據
        dates = []
        sizes = []
        
        # 僅使用最近10個備份
        for backup in self.backup.backups[:10]:
            db_file = os.path.join(backup["path"], "chroma.sqlite3")
            if os.path.exists(db_file):
                dates.append(backup["date"].strftime("%m-%d"))
                sizes.append(os.path.getsize(db_file) / (1024 * 1024))  # 轉換為MB
        
        # 反轉列表，使日期按時間順序顯示
        dates.reverse()
        sizes.reverse()
        
        if not dates:
            return
        
        # 創建圖表
        fig = plt.Figure(figsize=(3, 2), dpi=100)
        ax = fig.add_subplot(111)
        
        ax.plot(dates, sizes, 'o-', color='skyblue')
        ax.set_xlabel('日期', fontsize=8)
        ax.set_ylabel('大小 (MB)', fontsize=8)
        ax.set_title('備份大小趨勢', fontsize=10)
        
        # 設置x軸標籤角度
        plt.setp(ax.get_xticklabels(), rotation=45, ha='right', fontsize=6)
        ax.tick_params(axis='y', labelsize=6)
        
        fig.tight_layout()
        
        # 將圖表嵌入到tkinter視窗
        canvas = FigureCanvasTkAgg(fig, self.chart_container)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=BOTH, expand=YES)
    
    def create_backup_dialog(self):
        """顯示創建備份對話框"""
        if not self.backup.source_db_path or not self.backup.backup_dir:
            messagebox.showwarning("警告", "請先設置源數據庫和備份目錄")
            return
        
        # 創建對話框
        dialog = tk.Toplevel(self.root)
        dialog.title("創建新備份")
        dialog.geometry("400x200")
        dialog.resizable(False, False)
        dialog.grab_set()  # 模態對話框
        
        # 對話框內容
        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill=BOTH, expand=YES)
        
        ttk.Label(frame, text="備份描述:").pack(anchor=W, pady=(0, 5))
        
        description_var = tk.StringVar()
        description_entry = ttk.Entry(frame, textvariable=description_var, width=40)
        description_entry.pack(fill=X, pady=(0, 20))
        
        # 按鈕
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=X)
        
        ttk.Button(
            btn_frame,
            text="取消",
            command=dialog.destroy
        ).pack(side=RIGHT)
        
        ttk.Button(
            btn_frame,
            text="創建備份",
            style="Accent.TButton",
            command=lambda: self.create_backup(description_var.get(), dialog)
        ).pack(side=RIGHT, padx=5)
        
        # 設置焦點
        description_entry.focus_set()
    
    def create_backup(self, description, dialog):
        """創建新備份"""
        dialog.destroy()
        
        self.status_var.set("正在創建備份...")
        self.root.update_idletasks()
        
        def backup_thread():
            success = self.backup.create_backup(description)
            self.root.after(0, lambda: self.finalize_backup_creation(success))
        
        threading.Thread(target=backup_thread).start()
    
    def finalize_backup_creation(self, success):
        """完成備份創建"""
        if success:
            self.status_var.set("備份創建成功")
            self.refresh_ui()
            messagebox.showinfo("成功", "備份已成功創建")
        else:
            self.status_var.set("備份創建失敗")
            messagebox.showerror("錯誤", "創建備份時發生錯誤，請查看日誌了解詳情")
    
    def view_backup_details(self, event=None):
        """查看備份詳情"""
        selection = self.backups_tree.selection()
        if not selection:
            return
        
        self.view_backup_details_from_menu()
    
    def view_backup_details_from_menu(self):
        """從上下文選單查看備份詳情"""
        selection = self.backups_tree.selection()
        if not selection:
            return
        
        # 獲取選定項的索引
        item_id = selection[0]
        item_index = self.backups_tree.index(item_id)
        
        # 確保索引有效
        if item_index >= len(self.backup.backups):
            return
        
        backup = self.backup.backups[item_index]
        
        # 創建詳情對話框
        dialog = tk.Toplevel(self.root)
        dialog.title(f"備份詳情 - {backup['name']}")
        dialog.geometry("500x400")
        dialog.grab_set()
        
        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill=BOTH, expand=YES)
        
        # 基本信息
        info_frame = ttk.Frame(frame)
        info_frame.pack(fill=X, pady=(0, 20))
        
        ttk.Label(info_frame, text="基本信息", font=("TkDefaultFont", 12, "bold")).pack(anchor=W)
        
        info_text = f"名稱: {backup['name']}\n"
        info_text += f"建立日期: {backup['formatted_date']}\n"
        info_text += f"大小: {backup['size']}\n"
        info_text += f"路徑: {backup['path']}\n"
        
        # 檢查元數據文件
        metadata_path = os.path.join(backup['path'], "backup_metadata.json")
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
                
                if metadata.get("description"):
                    info_text += f"\n描述: {metadata['description']}\n"
                
                if metadata.get("backup_type"):
                    info_text += f"備份類型: {metadata['backup_type']}\n"
                
                if metadata.get("source_db"):
                    info_text += f"源數據庫: {metadata['source_db']}\n"
                
                if metadata.get("schedule_info"):
                    schedule_info = metadata["schedule_info"]
                    info_text += f"\n排程信息:\n"
                    info_text += f"間隔: {schedule_info.get('interval', '未知')}\n"
                    info_text += f"排程ID: {schedule_info.get('job_id', '未知')}\n"
            except Exception:
                info_text += "\n無法讀取元數據文件"
        
        info_label = ttk.Label(info_frame, text=info_text, justify=LEFT)
        info_label.pack(anchor=W, pady=5)
        
        # 數據庫信息
        db_frame = ttk.Frame(frame)
        db_frame.pack(fill=X)
        
        ttk.Label(db_frame, text="數據庫信息", font=("TkDefaultFont", 12, "bold")).pack(anchor=W)
        
        # 嘗試連接到備份的數據庫
        db_path = os.path.join(backup['path'], "chroma.sqlite3")
        
        if os.path.exists(db_path):
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                
                # 獲取表列表
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = cursor.fetchall()
                
                db_text = "表結構:\n"
                for table in tables:
                    table_name = table[0]
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
                    count = cursor.fetchone()[0]
                    db_text += f"- {table_name}: {count} 行\n"
                
                conn.close()
                
                ttk.Label(db_frame, text=db_text, justify=LEFT).pack(anchor=W, pady=5)
            except Exception as e:
                ttk.Label(db_frame, text=f"無法讀取數據庫: {str(e)}", justify=LEFT).pack(anchor=W, pady=5)
        else:
            ttk.Label(db_frame, text="數據庫文件不存在", justify=LEFT).pack(anchor=W, pady=5)
        
        # 按鈕
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=X, pady=(20, 0))
        
        ttk.Button(
            btn_frame,
            text="關閉",
            command=dialog.destroy
        ).pack(side=RIGHT)
        
        ttk.Button(
            btn_frame,
            text="還原此備份",
            command=lambda: [dialog.destroy(), self.restore_selected_backup()]
        ).pack(side=RIGHT, padx=5)
    
    def show_backup_context_menu(self, event):
        """顯示備份上下文選單"""
        selection = self.backups_tree.selection()
        if selection:
            self.backup_context_menu.post(event.x_root, event.y_root)
    
    def restore_backup_dialog(self):
        """顯示還原備份對話框"""
        selection = self.backups_tree.selection()
        if not selection:
            messagebox.showinfo("提示", "請先選擇要還原的備份")
            return
        
        # 獲取選定項的索引
        item_id = selection[0]
        item_index = self.backups_tree.index(item_id)
        
        # 確保索引有效
        if item_index >= len(self.backup.backups):
            return
        
        backup = self.backup.backups[item_index]
        
        # 創建對話框
        dialog = tk.Toplevel(self.root)
        dialog.title("還原備份")
        dialog.geometry("500x250")
        dialog.resizable(False, False)
        dialog.grab_set()
        
        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill=BOTH, expand=YES)
        
        ttk.Label(
            frame,
            text="還原選項",
            font=("TkDefaultFont", 14, "bold")
        ).pack(anchor=W, pady=(0, 10))
        
        ttk.Label(
            frame,
            text=f"選定的備份: {backup['name']} ({backup['formatted_date']})"
        ).pack(anchor=W, pady=(0, 20))
        
        # 還原選項
        options_frame = ttk.Frame(frame)
        options_frame.pack(fill=X, pady=(0, 20))
        
        restore_option = tk.StringVar(value="source")
        
        ttk.Radiobutton(
            options_frame,
            text="還原到源數據庫位置",
            variable=restore_option,
            value="source"
        ).pack(anchor=W, pady=2)
        
        ttk.Radiobutton(
            options_frame,
            text="還原到自訂位置",
            variable=restore_option,
            value="custom"
        ).pack(anchor=W, pady=2)
        
        custom_frame = ttk.Frame(options_frame)
        custom_frame.pack(fill=X, pady=(5, 0), padx=(20, 0))
        
        custom_path_var = tk.StringVar()
        
        ttk.Entry(custom_frame, textvariable=custom_path_var).pack(side=LEFT, fill=X, expand=YES)
        ttk.Button(
            custom_frame,
            text="瀏覽",
            command=lambda: custom_path_var.set(filedialog.askdirectory(
                title="選擇還原目標目錄",
                initialdir=str(Path.home())
            ))
        ).pack(side=LEFT, padx=(5, 0))
        
        # 警告信息
        ttk.Label(
            frame,
            text="警告: 還原操作將覆蓋目標位置的現有數據。過程中會創建安全備份。",
            foreground="red",
            wraplength=460
        ).pack(anchor=W, pady=(0, 20))
        
        # 按鈕
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=X)
        
        ttk.Button(
            btn_frame,
            text="取消",
            command=dialog.destroy
        ).pack(side=RIGHT)
        
        ttk.Button(
            btn_frame,
            text="還原",
            style="Accent.TButton",
            command=lambda: self.restore_backup(item_index, restore_option.get(), custom_path_var.get(), dialog)
        ).pack(side=RIGHT, padx=5)
    
    def restore_selected_backup(self):
        """還原選中的備份"""
        selection = self.backups_tree.selection()
        if not selection:
            messagebox.showinfo("提示", "請先選擇要還原的備份")
            return
        
        self.restore_backup_dialog()
    
    def restore_backup(self, backup_index, option, custom_path, dialog):
        """執行備份還原"""
        dialog.destroy()
        
        # 確認還原路徑
        restore_path = None
        if option == "source":
            restore_path = self.backup.source_db_path
        elif option == "custom" and custom_path:
            restore_path = custom_path
        else:
            messagebox.showerror("錯誤", "請指定有效的還原目標路徑")
            return
        
        # 確認還原操作
        if not messagebox.askyesno("確認還原", 
                                 f"確定要還原此備份到 {restore_path}?\n\n"
                                 f"警告: 此操作將覆蓋目標位置的所有現有數據!"):
            return
        
        self.status_var.set("正在還原備份...")
        self.root.update_idletasks()
        
        def restore_thread():
            success = self.backup.restore_backup(backup_index, restore_path)
            self.root.after(0, lambda: self.finalize_backup_restore(success, restore_path))
        
        threading.Thread(target=restore_thread).start()
    
    def finalize_backup_restore(self, success, restore_path):
        """完成備份還原"""
        if success:
            self.status_var.set("備份還原成功")
            messagebox.showinfo("成功", f"備份已成功還原到 {restore_path}")
        else:
            self.status_var.set("備份還原失敗")
            messagebox.showerror("錯誤", "還原備份時發生錯誤，請查看日誌了解詳情")
    
    def delete_backup_dialog(self):
        """顯示刪除備份確認對話框"""
        selection = self.backups_tree.selection()
        if not selection:
            messagebox.showinfo("提示", "請先選擇要刪除的備份")
            return
        
        # 獲取選定項的索引
        item_id = selection[0]
        item_index = self.backups_tree.index(item_id)
        
        # 確保索引有效
        if item_index >= len(self.backup.backups):
            return
        
        backup = self.backup.backups[item_index]
        
        # 確認刪除
        if messagebox.askyesno("確認刪除", 
                              f"確定要刪除備份 '{backup['name']}' ({backup['formatted_date']})?\n\n"
                              f"警告: 此操作無法撤銷!"):
            self.delete_backup(item_index)
    
    def delete_selected_backup(self):
        """刪除選中的備份"""
        self.delete_backup_dialog()
    
    def delete_backup(self, backup_index):
        """執行備份刪除"""
        self.status_var.set("正在刪除備份...")
        self.root.update_idletasks()
        
        success = self.backup.delete_backup(backup_index)
        
        if success:
            self.status_var.set("備份已刪除")
            self.refresh_ui()
        else:
            self.status_var.set("刪除備份失敗")
            messagebox.showerror("錯誤", "刪除備份時發生錯誤")
    
    def export_backup_dialog(self):
        """顯示導出備份對話框"""
        selection = self.backups_tree.selection()
        if not selection:
            messagebox.showinfo("提示", "請先選擇要導出的備份")
            return
        
        # 獲取選定項的索引
        item_id = selection[0]
        item_index = self.backups_tree.index(item_id)
        
        # 確保索引有效
        if item_index >= len(self.backup.backups):
            return
        
        backup = self.backup.backups[item_index]
        
        # 詢問保存位置
        file_path = filedialog.asksaveasfilename(
            title="導出備份",
            initialfile=f"{backup['name']}.zip",
            defaultextension=".zip",
            filetypes=[("ZIP文件", "*.zip")]
        )
        
        if file_path:
            self.export_backup(item_index, file_path)
    
    def export_selected_backup(self):
        """導出選中的備份"""
        self.export_backup_dialog()
    
    def export_backup(self, backup_index, file_path):
        """執行備份導出"""
        self.status_var.set("正在導出備份...")
        self.root.update_idletasks()
        
        def export_thread():
            success = self.backup.export_backup(backup_index, file_path)
            self.root.after(0, lambda: self.finalize_backup_export(success, file_path))
        
        threading.Thread(target=export_thread).start()
    
    def finalize_backup_export(self, success, file_path):
        """完成備份導出"""
        if success:
            self.status_var.set("備份導出成功")
            messagebox.showinfo("成功", f"備份已成功導出到 {file_path}")
        else:
            self.status_var.set("備份導出失敗")
            messagebox.showerror("錯誤", "導出備份時發生錯誤")
    
    def import_backup_dialog(self):
        """顯示導入備份對話框"""
        # 詢問ZIP文件位置
        file_path = filedialog.askopenfilename(
            title="導入備份",
            filetypes=[("ZIP文件", "*.zip"), ("所有文件", "*.*")]
        )
        
        if file_path:
            self.import_backup(file_path)
    
    def import_backup(self, file_path):
        """執行備份導入"""
        self.status_var.set("正在導入備份...")
        self.root.update_idletasks()
        
        def import_thread():
            success = self.backup.import_backup(file_path)
            self.root.after(0, lambda: self.finalize_backup_import(success))
        
        threading.Thread(target=import_thread).start()
    
    def finalize_backup_import(self, success):
        """完成備份導入"""
        if success:
            self.status_var.set("備份導入成功")
            self.refresh_ui()
            messagebox.showinfo("成功", "備份已成功導入")
        else:
            self.status_var.set("備份導入失敗")
            messagebox.showerror("錯誤", "導入備份時發生錯誤，請確保ZIP文件包含有效的ChromaDB備份")
    
    def schedule_backup_dialog(self):
        """顯示排程備份對話框"""
        if not self.backup.source_db_path or not self.backup.backup_dir:
            messagebox.showwarning("警告", "請先設置源數據庫和備份目錄")
            return
        
        # 創建對話框
        dialog = tk.Toplevel(self.root)
        dialog.title("排程備份")
        dialog.geometry("450x550")  # 增加高度以容納時間選擇器
        dialog.resizable(False, False)
        dialog.grab_set()
        
        # 使用主框架
        main_frame = ttk.Frame(dialog, padding=20)
        main_frame.pack(fill=BOTH, expand=YES)
        
        # 標題
        ttk.Label(
            main_frame,
            text="排程設置",
            font=("TkDefaultFont", 14, "bold")
        ).pack(anchor=W, pady=(0, 15))
        
        # 間隔選擇
        interval_frame = ttk.Frame(main_frame)
        interval_frame.pack(fill=X, pady=(0, 10)) # 減少 pady
        
        ttk.Label(interval_frame, text="備份間隔:").pack(anchor=W)
        
        interval_var = tk.StringVar(value="daily")
        
        intervals = [
            ("每小時 (忽略時間設定)", "hourly"), # 提示每小時忽略時間
            ("每天", "daily"),
            ("每週 (週一)", "weekly"), # 提示每週預設為週一
            ("每月 (1號)", "monthly")  # 提示每月預設為1號
        ]
        
        for text, value in intervals:
            ttk.Radiobutton(
                interval_frame,
                text=text,
                variable=interval_var,
                value=value
            ).pack(anchor=W, padx=(20, 0), pady=1) # 減少 pady
        
        # 時間選擇 (小時和分鐘)
        time_frame = ttk.Frame(main_frame)
        time_frame.pack(fill=X, pady=(5, 10)) # 減少 pady
        
        ttk.Label(time_frame, text="執行時間 (HH:MM):").pack(side=LEFT, anchor=W)
        
        hour_var = tk.StringVar(value="00")
        minute_var = tk.StringVar(value="00")
        
        # 小時 Spinbox
        ttk.Spinbox(
            time_frame,
            from_=0,
            to=23,
            textvariable=hour_var,
            width=3,
            format="%02.0f" # 格式化為兩位數
        ).pack(side=LEFT, padx=(5, 0))
        
        ttk.Label(time_frame, text=":").pack(side=LEFT, padx=2)
        
        # 分鐘 Spinbox
        ttk.Spinbox(
            time_frame,
            from_=0,
            to=59,
            textvariable=minute_var,
            width=3,
            format="%02.0f" # 格式化為兩位數
        ).pack(side=LEFT, padx=(0, 5))

        ttk.Label(time_frame, text="(每小時排程將忽略此設定)").pack(side=LEFT, padx=(5,0), anchor=W)

        # 描述
        ttk.Label(main_frame, text="備份描述:").pack(anchor=W, pady=(0, 5))
        
        description_var = tk.StringVar(value="排程備份")
        ttk.Entry(main_frame, textvariable=description_var, width=40).pack(fill=X, pady=(0, 10)) # 減少 pady
        
        # 保留數量
        keep_frame = ttk.Frame(main_frame)
        keep_frame.pack(fill=X, pady=(0, 10)) # 減少 pady
        
        ttk.Label(keep_frame, text="最多保留備份數量:").pack(side=LEFT)
        
        keep_count_var = tk.StringVar(value="7")
        ttk.Spinbox(
            keep_frame,
            from_=0,
            to=100,
            textvariable=keep_count_var,
            width=5
        ).pack(side=LEFT, padx=(5, 0))
        
        ttk.Label(
            keep_frame,
            text="(0表示不限制)"
        ).pack(side=LEFT, padx=(5, 0))
        
        # 分隔線
        ttk.Separator(main_frame, orient=HORIZONTAL).pack(fill=X, pady=10) # 減少 pady
        
        # 底部按鈕區
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=X, pady=(5, 0)) # 減少 pady
        
        cancel_btn = ttk.Button(
            btn_frame,
            text="取消",
            command=dialog.destroy,
            width=12
        )
        cancel_btn.pack(side=LEFT, padx=(0, 10))
        
        create_btn = ttk.Button(
            btn_frame,
            text="加入排程",
            width=15,
            command=lambda: self.create_schedule(
                interval_var.get(),
                description_var.get(),
                keep_count_var.get(),
                f"{hour_var.get()}:{minute_var.get()}", # 組合時間字串
                dialog
            )
        )
        create_btn.pack(side=LEFT)
        
        note_frame = ttk.Frame(main_frame)
        note_frame.pack(fill=X, pady=(10, 0)) # 減少 pady
        
        ttk.Label(
            note_frame,
            text="請確保點擊「加入排程」按鈕完成設置",
            foreground="blue"
        ).pack()

    def create_schedule(self, interval, description, keep_count_str, at_time_str, dialog):
        """創建備份排程"""
        dialog.destroy()
        
        try:
            keep_count = int(keep_count_str)
        except ValueError:
            keep_count = 0
        
        # 驗證時間格式
        try:
            time.strptime(at_time_str, "%H:%M")
        except ValueError:
            messagebox.showerror("錯誤", f"無效的時間格式: {at_time_str}. 請使用 HH:MM 格式.")
            self.status_var.set("創建排程失敗: 無效的時間格式")
            return

        # 如果是每小時排程，則 at_time 設為 None
        effective_at_time = at_time_str if interval != "hourly" else None

        success = self.backup.schedule_backup(interval, description, keep_count, effective_at_time)
        
        if success:
            self.status_var.set(f"已創建 {interval} 備份排程 (時間: {effective_at_time if effective_at_time else '每小時'})")
            self.refresh_scheduled_jobs()
            messagebox.showinfo("成功", f"已成功創建 {interval} 備份排程 (時間: {effective_at_time if effective_at_time else '每小時'})")
        else:
            self.status_var.set("創建排程失敗")
            messagebox.showerror("錯誤", "無法創建備份排程，請檢查日誌。")
    
    def quick_schedule(self, interval):
        """快速創建排程備份"""
        if not self.backup.source_db_path or not self.backup.backup_dir:
            messagebox.showwarning("警告", "請先設置源數據庫和備份目錄")
            return
        
        # 根據間隔設置描述和保留數量
        if interval == "hourly":
            description = "每小時自動備份"
            keep_count = 24
        elif interval == "daily":
            description = "每日自動備份"
            keep_count = 7
        elif interval == "weekly":
            description = "每週自動備份"
            keep_count = 4
        else:
            description = "自動備份"
            keep_count = 5
        
        # 確認創建
        if messagebox.askyesno("確認", f"確定要創建 {description} 排程?\n\n將保留最新的 {keep_count} 個備份"):
            success = self.backup.schedule_backup(interval, description, keep_count)
            
            if success:
                self.status_var.set(f"已創建 {interval} 備份排程")
                self.refresh_scheduled_jobs()
                messagebox.showinfo("成功", f"已成功創建 {interval} 備份排程")
            else:
                self.status_var.set("創建排程失敗")
                messagebox.showerror("錯誤", "無法創建備份排程")
    
    def cancel_selected_job(self):
        """取消選中的排程任務"""
        selection = self.jobs_tree.selection()
        if not selection:
            messagebox.showinfo("提示", "請先選擇要取消的排程任務")
            return
        
        # 獲取任務ID
        job_id = selection[0]
        
        # 確認取消
        if messagebox.askyesno("確認", "確定要取消此排程任務?"):
            success = self.backup.cancel_scheduled_backup(job_id)
            
            if success:
                self.status_var.set("已取消排程任務")
                self.refresh_scheduled_jobs()
            else:
                self.status_var.set("取消排程任務失敗")
                messagebox.showerror("錯誤", "無法取消排程任務")
    
    def run_selected_job(self):
        """立即執行選中的排程任務"""
        selection = self.jobs_tree.selection()
        if not selection:
            messagebox.showinfo("提示", "請先選擇要執行的排程任務")
            return
        
        # 獲取任務ID
        job_id = selection[0]
        
        # 確認執行
        if messagebox.askyesno("確認", "確定要立即執行此排程任務?"):
            # 獲取任務信息
            job_info = self.backup.scheduled_jobs.get(job_id)
            if not job_info:
                messagebox.showerror("錯誤", "找不到排程任務信息")
                return
            
            self.status_var.set("正在執行排程備份...")
            self.root.update_idletasks()
            
            def run_job_thread():
                success = self.backup._run_scheduled_backup(
                    job_id,
                    job_info["description"],
                    job_info["interval"],
                    job_info.get("at_time") # 傳遞 at_time
                )
                self.root.after(0, lambda: self.finalize_job_execution(success))
            
            threading.Thread(target=run_job_thread).start()
    
    def finalize_job_execution(self, success):
        """完成排程任務執行"""
        if success:
            self.status_var.set("排程備份執行完成")
            self.refresh_ui()
            messagebox.showinfo("成功", "排程備份任務已成功執行")
        else:
            self.status_var.set("排程備份執行失敗")
            messagebox.showerror("錯誤", "執行排程備份時發生錯誤")
    
    def view_scheduled_jobs(self):
        """查看所有排程任務"""
        jobs = self.backup.get_scheduled_jobs_info()
        
        if not jobs:
            messagebox.showinfo("排程任務", "當前沒有活動的排程任務")
            return
        
        # 創建對話框
        dialog = tk.Toplevel(self.root)
        dialog.title("排程任務列表")
        dialog.geometry("600x400")
        dialog.grab_set()
        
        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill=BOTH, expand=YES)
        
        ttk.Label(
            frame,
            text="排程備份任務",
            font=("TkDefaultFont", 14, "bold")
        ).pack(anchor=W, pady=(0, 15))
        
        # 創建表格
        columns = ("id", "interval", "description", "next_run", "keep_count", "at_time") # 新增 at_time
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=10)
        
        tree.heading("id", text="任務ID")
        tree.heading("interval", text="間隔")
        tree.heading("description", text="描述")
        tree.heading("next_run", text="下次執行")
        tree.heading("keep_count", text="保留數量")
        tree.heading("at_time", text="執行時間") # 新增
        
        tree.column("id", width=120)
        tree.column("interval", width=70)
        tree.column("description", width=120)
        tree.column("next_run", width=130)
        tree.column("keep_count", width=70)
        tree.column("at_time", width=70) # 新增
        
        # 添加數據
        for job in jobs:
            tree.insert(
                "", "end",
                values=(
                    job["id"],
                    job["interval"],
                    job["description"],
                    job["next_run"],
                    job["keep_count"],
                    job.get("at_time", "N/A") # 新增
                )
            )
        
        # 添加滾動條
        scrollbar = ttk.Scrollbar(frame, orient=VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        tree.pack(side=LEFT, fill=BOTH, expand=YES)
        scrollbar.pack(side=RIGHT, fill=Y)
        
        # 按鈕
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=X, pady=10, padx=20)
        
        ttk.Button(
            btn_frame,
            text="關閉",
            command=dialog.destroy
        ).pack(side=RIGHT)
        
        ttk.Button(
            btn_frame,
            text="新增排程",
            command=lambda: [dialog.destroy(), self.schedule_backup_dialog()]
        ).pack(side=RIGHT, padx=5)
    
    def view_backup_history(self):
        """查看備份歷史"""
        history = self.backup.backup_history
        
        # 創建對話框
        dialog = tk.Toplevel(self.root)
        dialog.title("備份歷史")
        dialog.geometry("600x400")
        dialog.grab_set()
        
        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill=BOTH, expand=YES)
        
        ttk.Label(
            frame,
            text="備份操作歷史",
            font=("TkDefaultFont", 14, "bold")
        ).pack(anchor=W, pady=(0, 15))
        
        # 創建表格
        columns = ("date", "name", "status", "description")
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=10)
        
        tree.heading("date", text="日期")
        tree.heading("name", text="名稱")
        tree.heading("status", text="狀態")
        tree.heading("description", text="描述")
        
        tree.column("date", width=150)
        tree.column("name", width=200)
        tree.column("status", width=80)
        tree.column("description", width=200)
        
        # 添加數據
        for entry in sorted(history, key=lambda x: x["date"], reverse=True):
            tree.insert(
                "", "end",
                values=(
                    entry["date"].strftime("%Y-%m-%d %H:%M:%S"),
                    entry["name"],
                    entry["status"],
                    entry.get("description", "")
                ),
                tags=(entry["status"],)
            )
        
        # 設置標籤顏色
        tree.tag_configure("success", background="#e6ffe6")
        tree.tag_configure("failed", background="#ffe6e6")
        
        # 添加滾動條
        scrollbar = ttk.Scrollbar(frame, orient=VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        tree.pack(side=LEFT, fill=BOTH, expand=YES)
        scrollbar.pack(side=RIGHT, fill=Y)
        
        # 按鈕
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=X, pady=10, padx=20)
        
        ttk.Button(
            btn_frame,
            text="關閉",
            command=dialog.destroy
        ).pack(side=RIGHT)
    
    def view_db_info(self):
        """查看數據庫詳細信息"""
        if not self.backup.source_db_path:
            messagebox.showinfo("提示", "請先設置源數據庫")
            return
        
        info = self.backup.get_db_info()
        
        # 創建對話框
        dialog = tk.Toplevel(self.root)
        dialog.title("數據庫信息")
        dialog.geometry("500x400")
        dialog.grab_set()
        
        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill=BOTH, expand=YES)
        
        ttk.Label(
            frame,
            text="數據庫詳細信息",
            font=("TkDefaultFont", 14, "bold")
        ).pack(anchor=W, pady=(0, 15))
        
        if info["status"] == "ok":
            # 基本信息
            basic_frame = ttk.LabelFrame(frame, text="基本信息", padding=10)
            basic_frame.pack(fill=X, pady=(0, 10))
            
            basic_text = f"路徑: {info['path']}\n"
            basic_text += f"大小: {info['size']}\n"
            basic_text += f"最後修改: {info['last_modified']}\n"
            basic_text += f"數據庫版本: {info['db_version']}"
            
            ttk.Label(basic_frame, text=basic_text, justify=LEFT).pack(anchor=W)
            
            # 表格信息
            tables_frame = ttk.LabelFrame(frame, text="表格信息", padding=10)
            tables_frame.pack(fill=BOTH, expand=YES, pady=(0, 10))
            
            # 創建表格
            columns = ("table", "count")
            tree = ttk.Treeview(tables_frame, columns=columns, show="headings", height=8)
            
            tree.heading("table", text="表名")
            tree.heading("count", text="行數")
            
            tree.column("table", width=200)
            tree.column("count", width=100)
            
            # 添加數據
            for table, count in info["tables"].items():
                tree.insert(
                    "", "end",
                    values=(table, count)
                )
            
            # 添加滾動條
            scrollbar = ttk.Scrollbar(tables_frame, orient=VERTICAL, command=tree.yview)
            tree.configure(yscrollcommand=scrollbar.set)
            
            tree.pack(side=LEFT, fill=BOTH, expand=YES)
            scrollbar.pack(side=RIGHT, fill=Y)
            
            # 嵌入向量信息
            embeddings_frame = ttk.LabelFrame(frame, text="嵌入向量", padding=10)
            embeddings_frame.pack(fill=X)
            
            embedding_text = f"嵌入向量數量: {info['embeddings_count']}"
            
            ttk.Label(embeddings_frame, text=embedding_text, justify=LEFT).pack(anchor=W)
        else:
            # 錯誤信息
            error_text = f"獲取數據庫信息時出錯:\n{info.get('error', '未知錯誤')}"
            
            ttk.Label(frame, text=error_text, foreground="red").pack(anchor=W)
        
        # 按鈕
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=X, pady=10)
        
        ttk.Button(
            btn_frame,
            text="關閉",
            command=dialog.destroy
        ).pack(side=RIGHT)
        
        ttk.Button(
            btn_frame,
            text="刷新",
            command=lambda: [dialog.destroy(), self.view_db_info()]
        ).pack(side=RIGHT, padx=5)
    
    def toggle_theme(self):
        """切換深色/淺色主題"""
        if self.current_theme == "darkly":
            self.current_theme = "cosmo"  # 淺色主題
            ttk.Style().theme_use("cosmo")
        else:
            self.current_theme = "darkly"  # 深色主題
            ttk.Style().theme_use("darkly")
        
        # 保存配置
        self.config["theme"] = self.current_theme
        self.save_config()
    
    def show_about(self):
        """顯示關於對話框"""
        about_text = "ChromaDB 備份工具\n\n"
        about_text += "版本: 1.0.0\n\n"
        about_text += "這是一個用於備份和管理ChromaDB數據庫的工具，支持手動和排程備份、還原、導入/導出等功能。\n\n"
        about_text += "功能包括:\n"
        about_text += "- 手動和排程備份\n"
        about_text += "- 備份還原\n"
        about_text += "- 備份導入/導出\n"
        about_text += "- 備份管理\n"
        about_text += "- 數據庫統計\n"
        
        messagebox.showinfo("關於", about_text)
    
    def open_log_file(self):
        """打開日誌文件"""
        log_path = "chroma_backup.log"
        
        if os.path.exists(log_path):
            # 創建日誌查看器窗口
            log_window = tk.Toplevel(self.root)
            log_window.title("日誌查看器")
            log_window.geometry("800x600")
            
            frame = ttk.Frame(log_window, padding=10)
            frame.pack(fill=BOTH, expand=YES)
            
            # 添加日誌內容
            text_area = tk.Text(frame, wrap=tk.WORD)
            
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    log_content = f.read()
            except UnicodeDecodeError:
                try:
                    with open(log_path, "r", encoding="gbk") as f:
                        log_content = f.read()
                except:
                    log_content = "無法讀取日誌文件"
            
            text_area.insert(tk.END, log_content)
            text_area.config(state=tk.DISABLED)
            
            scrollbar = ttk.Scrollbar(frame, orient=VERTICAL, command=text_area.yview)
            text_area.configure(yscrollcommand=scrollbar.set)
            
            text_area.pack(side=LEFT, fill=BOTH, expand=YES)
            scrollbar.pack(side=LEFT, fill=Y)
            
            # 添加刷新和清空按鈕
            button_frame = ttk.Frame(log_window)
            button_frame.pack(fill=X, pady=10)
            
            ttk.Button(
                button_frame, 
                text="刷新", 
                command=lambda: self.refresh_log_view(text_area, log_path)
            ).pack(side=LEFT, padx=5)
            
            ttk.Button(
                button_frame, 
                text="清空日誌", 
                command=lambda: self.clear_log_file(text_area, log_path)
            ).pack(side=LEFT, padx=5)
        else:
            messagebox.showinfo("提示", "日誌文件不存在")
    
    def refresh_log_view(self, text_area, log_path):
        """刷新日誌查看器內容"""
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                log_content = f.read()
        except UnicodeDecodeError:
            try:
                with open(log_path, "r", encoding="gbk") as f:
                    log_content = f.read()
            except:
                log_content = "無法讀取日誌文件"
        
        text_area.config(state=tk.NORMAL)
        text_area.delete("1.0", tk.END)
        text_area.insert(tk.END, log_content)
        text_area.config(state=tk.DISABLED)
    
    def clear_log_file(self, text_area, log_path):
        """清空日誌文件"""
        if messagebox.askyesno("確認", "確定要清空日誌文件嗎？"):
            try:
                with open(log_path, "w") as f:
                    f.write("")
                
                text_area.config(state=tk.NORMAL)
                text_area.delete("1.0", tk.END)
                text_area.config(state=tk.DISABLED)
                
                messagebox.showinfo("成功", "日誌文件已清空")
            except Exception as e:
                messagebox.showerror("錯誤", f"清空日誌文件時出錯: {str(e)}")
    
    def open_backup_reader(self):
        """打開備份閱讀器"""
        try:
            import subprocess
            import sys
            
            # 啟動備份閱讀器
            subprocess.Popen([sys.executable, "chroma_view2.py"])
            
            self.status_var.set("已啟動備份閱讀器")
        except Exception as e:
            self.status_var.set("啟動備份閱讀器失敗")
            messagebox.showerror("錯誤", f"無法啟動備份閱讀器: {str(e)}")
    
    def load_config(self):
        """載入配置"""
        default_config = {
            "last_source_db": "",
            "last_backup_dir": "",
            "theme": "darkly"
        }
        
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                return default_config
        
        return default_config
    
    def save_config(self):
        """保存配置"""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            self.backup.logger.error(f"保存配置時出錯: {str(e)}")
    
    def run_scheduler(self):
        """運行排程器線程"""
        while self.scheduler_running:
            self.backup.run_scheduler()
            time.sleep(1)


def main():
    """程序入口點"""
    root = ttk.Window(themename="darkly")
    app = ChromaDBBackupUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()

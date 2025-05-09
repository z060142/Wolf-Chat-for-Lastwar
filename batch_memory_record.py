#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Wolf Chat 批次記憶備份工具

自動掃描chat_logs資料夾，針對所有日誌檔案執行記憶備份
"""

import os
import re
import sys
import time
import argparse
import subprocess
import logging
from datetime import datetime
from typing import List, Optional, Tuple

# 設置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("batch_backup.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("BatchMemoryBackup")

def find_log_files(log_dir: str = "chat_logs") -> List[Tuple[str, str]]:
    """
    掃描指定目錄，找出所有符合YYYY-MM-DD.log格式的日誌文件
    
    返回: [(日期字符串, 文件路徑), ...]，按日期排序
    """
    date_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2})\.log$')
    log_files = []
    
    # 確保目錄存在
    if not os.path.exists(log_dir) or not os.path.isdir(log_dir):
        logger.error(f"目錄不存在或不是有效目錄: {log_dir}")
        return []
    
    # 掃描目錄
    for filename in os.listdir(log_dir):
        match = date_pattern.match(filename)
        if match:
            date_str = match.group(1)
            file_path = os.path.join(log_dir, filename)
            try:
                # 驗證日期格式
                datetime.strptime(date_str, "%Y-%m-%d")
                log_files.append((date_str, file_path))
            except ValueError:
                logger.warning(f"發現無效的日期格式: {filename}")
    
    # 按日期排序
    log_files.sort(key=lambda x: x[0])
    return log_files

def process_log_file(date_str: str, backup_script: str = "memory_backup.py") -> bool:
    """
    為指定日期的日誌文件執行記憶備份
    
    Parameters:
        date_str: 日期字符串，格式為YYYY-MM-DD
        backup_script: 備份腳本路徑
    
    Returns:
        bool: 操作是否成功
    """
    logger.info(f"開始處理日期 {date_str} 的日誌")
    
    try:
        # 構建命令
        cmd = [sys.executable, backup_script, "--backup", "--date", date_str]
        
        # 執行命令
        logger.info(f"執行命令: {' '.join(cmd)}")
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False  # 不要在命令失敗時拋出異常
        )
        
        # 檢查結果
        if process.returncode == 0:
            logger.info(f"日期 {date_str} 的處理完成")
            return True
        else:
            logger.error(f"處理日期 {date_str} 失敗: {process.stderr}")
            return False
    
    except Exception as e:
        logger.error(f"處理日期 {date_str} 時發生異常: {str(e)}")
        return False

def batch_process(log_dir: str = "chat_logs", backup_script: str = "memory_backup.py", 
                 date_range: Optional[Tuple[str, str]] = None, 
                 wait_seconds: int = 5) -> Tuple[int, int]:
    """
    批次處理多個日誌文件
    
    Parameters:
        log_dir: 日誌目錄路徑
        backup_script: 備份腳本路徑
        date_range: (開始日期, 結束日期)，用於限制處理範圍，格式為YYYY-MM-DD
        wait_seconds: 每個文件處理後的等待時間（秒）
    
    Returns:
        (成功數量, 總數量)
    """
    log_files = find_log_files(log_dir)
    
    if not log_files:
        logger.warning(f"在 {log_dir} 中未找到有效的日誌文件")
        return (0, 0)
    
    logger.info(f"找到 {len(log_files)} 個日誌文件")
    
    # 如果指定了日期範圍，過濾文件
    if date_range:
        start_date, end_date = date_range
        filtered_files = [(date_str, path) for date_str, path in log_files 
                         if start_date <= date_str <= end_date]
        logger.info(f"根據日期範圍 {start_date} 到 {end_date} 過濾後剩餘 {len(filtered_files)} 個文件")
        log_files = filtered_files
    
    success_count = 0
    total_count = len(log_files)
    
    for i, (date_str, file_path) in enumerate(log_files):
        logger.info(f"處理進度: {i+1}/{total_count} - 日期: {date_str}")
        
        if process_log_file(date_str, backup_script):
            success_count += 1
        
        # 若不是最後一個文件，等待一段時間再處理下一個
        if i < total_count - 1:
            logger.info(f"等待 {wait_seconds} 秒後處理下一個文件...")
            time.sleep(wait_seconds)
    
    return (success_count, total_count)

def parse_date_arg(date_arg: str) -> Optional[str]:
    """解析日期參數，確保格式為YYYY-MM-DD"""
    if not date_arg:
        return None
    
    try:
        parsed_date = datetime.strptime(date_arg, "%Y-%m-%d")
        return parsed_date.strftime("%Y-%m-%d")
    except ValueError:
        logger.error(f"無效的日期格式: {date_arg}，請使用YYYY-MM-DD格式")
        return None

def main():
    parser = argparse.ArgumentParser(description='Wolf Chat 批次記憶備份工具')
    parser.add_argument('--log-dir', default='chat_logs', help='日誌檔案目錄，預設為 chat_logs')
    parser.add_argument('--script', default='memory_backup.py', help='記憶備份腳本路徑，預設為 memory_backup.py')
    parser.add_argument('--start-date', help='開始日期（含），格式為 YYYY-MM-DD')
    parser.add_argument('--end-date', help='結束日期（含），格式為 YYYY-MM-DD')
    parser.add_argument('--wait', type=int, default=5, help='每個檔案處理間隔時間（秒），預設為 5 秒')
    
    args = parser.parse_args()
    
    # 驗證日期參數
    start_date = parse_date_arg(args.start_date)
    end_date = parse_date_arg(args.end_date)
    
    # 如果只有一個日期參數，將兩個都設為該日期（僅處理該日期）
    if start_date and not end_date:
        end_date = start_date
    elif end_date and not start_date:
        start_date = end_date
    
    date_range = (start_date, end_date) if start_date and end_date else None
    
    logger.info("開始批次記憶備份流程")
    logger.info(f"日誌目錄: {args.log_dir}")
    logger.info(f"備份腳本: {args.script}")
    if date_range:
        logger.info(f"日期範圍: {date_range[0]} 到 {date_range[1]}")
    else:
        logger.info("處理所有找到的日誌檔案")
    logger.info(f"等待間隔: {args.wait} 秒")
    
    start_time = time.time()
    success, total = batch_process(
        log_dir=args.log_dir,
        backup_script=args.script,
        date_range=date_range,
        wait_seconds=args.wait
    )
    end_time = time.time()
    
    duration = end_time - start_time
    logger.info(f"批次處理完成。成功: {success}/{total}，耗時: {duration:.2f} 秒")
    
    if success < total:
        logger.warning("部分日誌檔案處理失敗，請查看日誌瞭解詳情")
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
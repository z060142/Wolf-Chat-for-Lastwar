#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Wolf Chat 記憶備份工具

用於手動執行記憶備份或啟動定時調度器
"""

import sys
import argparse
import datetime
from memory_manager import run_memory_backup_manual, MemoryScheduler # Updated import
import config # Import config to access default schedule times

def main():
    parser = argparse.ArgumentParser(description='Wolf Chat 記憶備份工具')
    parser.add_argument('--backup', action='store_true', help='執行一次性備份 (預設為昨天，除非指定 --date)')
    parser.add_argument('--date', type=str, help='處理指定日期的日誌 (YYYY-MM-DD格式) for --backup')
    parser.add_argument('--schedule', action='store_true', help='啟動定時調度器')
    parser.add_argument('--hour', type=int, help='備份時間（小時，0-23）for --schedule')
    parser.add_argument('--minute', type=int, help='備份時間（分鐘，0-59）for --schedule')
    
    args = parser.parse_args()
    
    if args.backup:
        # The date logic is now handled inside run_memory_backup_manual
        run_memory_backup_manual(args.date)
    elif args.schedule:
        scheduler = MemoryScheduler()
        # Use provided hour/minute or fallback to config defaults
        backup_hour = args.hour if args.hour is not None else getattr(config, 'MEMORY_BACKUP_HOUR', 0)
        backup_minute = args.minute if args.minute is not None else getattr(config, 'MEMORY_BACKUP_MINUTE', 0)
        
        scheduler.schedule_daily_backup(backup_hour, backup_minute)
        scheduler.start()
    else:
        print("請指定操作: --backup 或 --schedule")
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()

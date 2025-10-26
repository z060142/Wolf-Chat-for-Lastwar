import os
import sys
import shutil
import datetime
import time
import schedule
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import threading
import json
import chromadb
from chromadb.config import Settings
import logging
import sys
import locale

# 設置日誌
log_file_handler = logging.FileHandler("chroma_backup.log", encoding='utf-8')
console_handler = logging.StreamHandler()

logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[log_file_handler, console_handler])
logger = logging.getLogger(__name__)

class ChromaBackupApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ChromaDB 備份管理工具")
        self.root.geometry("900x600")
        
        # 應用程式設定
        self.config = self.load_config()
        
        # 建立UI
        self.create_ui()
        
        # 初始化備份任務
        self.backup_thread = None
        self.scheduled_job = None
        self.setup_scheduled_backup()
    
    def load_config(self):
        """載入應用程式設定"""
        default_config = {
            "source_db_path": "",
            "backup_dir": os.path.join(os.path.expanduser("~"), "ChromaBackups"),
            "backup_time": "03:00",
            "backup_interval": "daily",
            "retention_days": 30,
            "last_backup": None,
            "collections": []
        }
        
        config_path = os.path.join(os.path.expanduser("~"), ".chroma_backup_config.json")
        
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    return {**default_config, **json.load(f)}
            return default_config
        except Exception as e:
            logger.error(f"讀取設定檔失敗: {e}")
            return default_config
    
    def save_config(self):
        """儲存應用程式設定"""
        config_path = os.path.join(os.path.expanduser("~"), ".chroma_backup_config.json")
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            logger.info("設定已儲存")
        except Exception as e:
            logger.error(f"儲存設定檔失敗: {e}")
    
    def create_ui(self):
        """建立使用者介面"""
        # 建立框架
        self.main_frame = ttk.Notebook(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 設定標籤頁
        self.setup_tab = ttk.Frame(self.main_frame)
        self.query_tab = ttk.Frame(self.main_frame)
        self.logs_tab = ttk.Frame(self.main_frame)
        
        self.main_frame.add(self.setup_tab, text="備份設定")
        self.main_frame.add(self.query_tab, text="資料查詢")
        self.main_frame.add(self.logs_tab, text="日誌")
        
        # 設定標籤頁內容
        self.create_setup_tab()
        self.create_query_tab()
        self.create_logs_tab()
        
        # 狀態列
        self.status_var = tk.StringVar()
        self.status_var.set("就緒")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    
    def create_setup_tab(self):
        """建立備份設定標籤頁"""
        frame = ttk.LabelFrame(self.setup_tab, text="備份設定")
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 來源資料庫路徑
        ttk.Label(frame, text="ChromaDB 路徑:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.source_var = tk.StringVar(value=self.config["source_db_path"])
        ttk.Entry(frame, textvariable=self.source_var, width=50).grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        ttk.Button(frame, text="瀏覽", command=self.browse_source).grid(row=0, column=2, sticky=tk.W, padx=5, pady=5)
        
        # 備份目錄
        ttk.Label(frame, text="備份目錄:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.backup_dir_var = tk.StringVar(value=self.config["backup_dir"])
        ttk.Entry(frame, textvariable=self.backup_dir_var, width=50).grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        ttk.Button(frame, text="瀏覽", command=self.browse_backup_dir).grid(row=1, column=2, sticky=tk.W, padx=5, pady=5)
        
        # 備份時間
        ttk.Label(frame, text="備份時間:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.backup_time_var = tk.StringVar(value=self.config["backup_time"])
        ttk.Entry(frame, textvariable=self.backup_time_var, width=10).grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        ttk.Label(frame, text="格式: HH:MM (24小時制)").grid(row=2, column=2, sticky=tk.W, padx=5, pady=5)
        
        # 備份間隔
        ttk.Label(frame, text="備份間隔:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        self.backup_interval_var = tk.StringVar(value=self.config["backup_interval"])
        interval_combo = ttk.Combobox(frame, textvariable=self.backup_interval_var, width=10)
        interval_combo['values'] = ('daily', 'weekly', 'monthly')
        interval_combo.grid(row=3, column=1, sticky=tk.W, padx=5, pady=5)
        
        # 保留天數
        ttk.Label(frame, text="保留天數:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=5)
        self.retention_var = tk.StringVar(value=str(self.config["retention_days"]))
        ttk.Entry(frame, textvariable=self.retention_var, width=10).grid(row=4, column=1, sticky=tk.W, padx=5, pady=5)
        
        # 上次備份時間
        ttk.Label(frame, text="上次備份:").grid(row=5, column=0, sticky=tk.W, padx=5, pady=5)
        self.last_backup_var = tk.StringVar(value=self.config["last_backup"] or "尚未備份")
        ttk.Label(frame, textvariable=self.last_backup_var).grid(row=5, column=1, sticky=tk.W, padx=5, pady=5)
        
        # 按鈕
        button_frame = ttk.Frame(frame)
        button_frame.grid(row=6, column=0, columnspan=3, pady=10)
        
        ttk.Button(button_frame, text="儲存設定", command=self.save_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="立即備份", command=self.start_backup).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="顯示集合", command=self.list_collections).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="停止備份服務", command=self.stop_scheduled_backup).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="啟動備份服務", command=self.setup_scheduled_backup).pack(side=tk.LEFT, padx=5)
        
        # 集合列表
        ttk.Label(frame, text="資料集合:").grid(row=7, column=0, sticky=tk.W, padx=5, pady=5)
        self.collections_frame = ttk.Frame(frame)
        self.collections_frame.grid(row=8, column=0, columnspan=3, sticky=tk.W+tk.E, padx=5, pady=5)
        
        self.collections_tree = ttk.Treeview(self.collections_frame, columns=("name",), show="headings", height=8)
        self.collections_tree.heading("name", text="集合名稱")
        self.collections_tree.column("name", width=400)
        self.collections_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(self.collections_frame, orient=tk.VERTICAL, command=self.collections_tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.collections_tree.configure(yscrollcommand=scrollbar.set)
        
    def create_query_tab(self):
        """建立資料查詢標籤頁"""
        frame = ttk.LabelFrame(self.query_tab, text="查詢資料")
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 選擇資料庫
        ttk.Label(frame, text="選擇資料庫:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.db_type_var = tk.StringVar(value="current")
        ttk.Radiobutton(frame, text="目前資料庫", variable=self.db_type_var, value="current").grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        ttk.Radiobutton(frame, text="備份資料庫", variable=self.db_type_var, value="backup").grid(row=0, column=2, sticky=tk.W, padx=5, pady=5)
        
        # 備份日期選擇
        ttk.Label(frame, text="備份日期:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.backup_date_var = tk.StringVar()
        self.backup_combo = ttk.Combobox(frame, textvariable=self.backup_date_var, width=30, state="readonly")
        self.backup_combo.grid(row=1, column=1, columnspan=2, sticky=tk.W, padx=5, pady=5)
        self.backup_combo.bind("<<ComboboxSelected>>", self.on_backup_selected)
        ttk.Button(frame, text="刷新", command=self.refresh_backups).grid(row=1, column=3, sticky=tk.W, padx=5, pady=5)
        
        # 集合選擇
        ttk.Label(frame, text="選擇集合:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.query_collection_var = tk.StringVar()
        self.query_collection_combo = ttk.Combobox(frame, textvariable=self.query_collection_var, width=30, state="readonly")
        self.query_collection_combo.grid(row=2, column=1, columnspan=2, sticky=tk.W, padx=5, pady=5)
        
        # 查詢文字
        ttk.Label(frame, text="查詢文字:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        self.query_text_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.query_text_var, width=50).grid(row=3, column=1, columnspan=2, sticky=tk.W+tk.E, padx=5, pady=5)
        
        # 查詢參數
        param_frame = ttk.LabelFrame(frame, text="查詢參數")
        param_frame.grid(row=4, column=0, columnspan=4, sticky=tk.W+tk.E, padx=5, pady=5)
        
        ttk.Label(param_frame, text="結果數量:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.n_results_var = tk.StringVar(value="5")
        ttk.Entry(param_frame, textvariable=self.n_results_var, width=5).grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        # 查詢按鈕
        ttk.Button(frame, text="執行查詢", command=self.execute_query).grid(row=5, column=0, columnspan=4, pady=10)
        
        # 結果區域
        result_frame = ttk.LabelFrame(frame, text="查詢結果")
        result_frame.grid(row=6, column=0, columnspan=4, sticky=tk.W+tk.E+tk.N+tk.S, padx=5, pady=5)
        result_frame.grid_rowconfigure(0, weight=1)
        result_frame.grid_columnconfigure(0, weight=1)
        
        self.result_text = tk.Text(result_frame, wrap=tk.WORD, width=80, height=15)
        self.result_text.grid(row=0, column=0, sticky=tk.W+tk.E+tk.N+tk.S, padx=5, pady=5)
        
        result_scrollbar = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=self.result_text.yview)
        result_scrollbar.grid(row=0, column=1, sticky=tk.N+tk.S)
        self.result_text.configure(yscrollcommand=result_scrollbar.set)
        
        # 初始化備份列表
        self.refresh_backups()
    
    def create_logs_tab(self):
        """建立日誌標籤頁"""
        frame = ttk.Frame(self.logs_tab)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.log_text = tk.Text(frame, wrap=tk.WORD, width=80, height=20)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        log_scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.log_text.yview)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        
        button_frame = ttk.Frame(self.logs_tab)
        button_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(button_frame, text="刷新日誌", command=self.refresh_logs).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="清除日誌", command=self.clear_logs).pack(side=tk.LEFT, padx=5)
        
        # 初始載入日誌
        self.refresh_logs()
    
    def browse_source(self):
        """選擇ChromaDB來源目錄"""
        directory = filedialog.askdirectory(title="選擇ChromaDB目錄")
        if directory:
            self.source_var.set(directory)
    
    def browse_backup_dir(self):
        """選擇備份目錄"""
        directory = filedialog.askdirectory(title="選擇備份目錄")
        if directory:
            self.backup_dir_var.set(directory)
    
    def save_settings(self):
        """儲存設定"""
        try:
            self.config["source_db_path"] = self.source_var.get()
            self.config["backup_dir"] = self.backup_dir_var.get()
            self.config["backup_time"] = self.backup_time_var.get()
            self.config["backup_interval"] = self.backup_interval_var.get()
            self.config["retention_days"] = int(self.retention_var.get())
            
            # 確保備份目錄存在
            os.makedirs(self.config["backup_dir"], exist_ok=True)
            
            self.save_config()
            
            # 更新排程
            self.setup_scheduled_backup()
            
            messagebox.showinfo("成功", "設定已儲存")
            logger.info("設定已更新")
        except Exception as e:
            messagebox.showerror("錯誤", f"儲存設定時發生錯誤: {e}")
            logger.error(f"儲存設定時發生錯誤: {e}")
    
    def list_collections(self):
        """列出ChromaDB中的集合"""
        try:
            if not self.config["source_db_path"]:
                messagebox.showwarning("警告", "請先設定ChromaDB路徑")
                return
            
            # 清空當前列表
            for item in self.collections_tree.get_children():
                self.collections_tree.delete(item)
            
            # 連接ChromaDB
            client = chromadb.PersistentClient(path=self.config["source_db_path"])
            collections = client.list_collections()
            
            # 更新配置
            self.config["collections"] = [coll.name for coll in collections]
            self.save_config()
            
            # 更新顯示
            for coll in collections:
                self.collections_tree.insert("", tk.END, values=(coll.name,))
            
            # 更新查詢標籤頁的集合選擇
            self.query_collection_combo['values'] = self.config["collections"]
            if self.config["collections"]:
                self.query_collection_combo.current(0)
            
            self.status_var.set(f"找到 {len(collections)} 個集合")
            logger.info(f"列出了 {len(collections)} 個集合")
        except Exception as e:
            messagebox.showerror("錯誤", f"獲取集合列表失敗: {e}")
            logger.error(f"獲取集合列表失敗: {e}")
    
    def start_backup(self):
        """立即啟動備份程序"""
        if not self.config["source_db_path"]:
            messagebox.showwarning("警告", "請先設定ChromaDB路徑")
            return
        
        if self.backup_thread and self.backup_thread.is_alive():
            messagebox.showinfo("資訊", "備份已在進行中")
            return
        
        self.backup_thread = threading.Thread(target=self.perform_backup)
        self.backup_thread.daemon = True
        self.backup_thread.start()
        
        self.status_var.set("備份進行中...")
    
    def perform_backup(self):
        """執行備份操作"""
        try:
            source_path = self.config["source_db_path"]
            backup_dir = self.config["backup_dir"]
            
            # 確保來源路徑存在
            if not os.path.exists(source_path):
                raise FileNotFoundError(f"ChromaDB路徑不存在: {source_path}")
            
            # 確保備份目錄存在
            os.makedirs(backup_dir, exist_ok=True)
            
            # 建立備份名稱 (格式: chroma_backup_YYYY-MM-DD_HH-MM-SS)
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            backup_name = f"chroma_backup_{timestamp}"
            backup_path = os.path.join(backup_dir, backup_name)
            
            # 備份資料庫
            logger.info(f"開始備份: {source_path} -> {backup_path}")
            self.root.after(0, lambda: self.status_var.set(f"正在備份: {backup_name}..."))
            
            # 檢查是否是目錄模式的ChromaDB
            if os.path.isdir(source_path):
                # 複製整個目錄
                shutil.copytree(source_path, backup_path)
            else:
                # 如果是單一檔案模式，複製檔案
                shutil.copy2(source_path, backup_path)
            
            # 更新上次備份時間
            self.config["last_backup"] = timestamp
            self.save_config()
            
            # 清理舊備份
            self.cleanup_old_backups()
            
            logger.info(f"備份完成: {backup_path}")
            self.root.after(0, lambda: self.status_var.set(f"備份完成: {backup_name}"))
            self.root.after(0, lambda: self.last_backup_var.set(timestamp))
            self.root.after(0, lambda: self.refresh_backups())
            self.root.after(0, lambda: messagebox.showinfo("成功", f"備份已完成\n{backup_path}"))
        except Exception as e:
            error_msg = f"備份失敗: {e}"
            logger.error(error_msg)
            self.root.after(0, lambda: self.status_var.set("備份失敗"))
            self.root.after(0, lambda: messagebox.showerror("錯誤", error_msg))
    
    def cleanup_old_backups(self):
        """清理過期的備份"""
        try:
            retention_days = self.config["retention_days"]
            backup_dir = self.config["backup_dir"]
            
            if retention_days <= 0:
                logger.info("備份保留期設為無限，跳過清理")
                return
            
            # 計算截止日期
            cutoff_date = datetime.datetime.now() - datetime.timedelta(days=retention_days)
            
            # 獲取所有備份
            backup_folders = [f for f in os.listdir(backup_dir) if f.startswith("chroma_backup_")]
            
            removed_count = 0
            for folder in backup_folders:
                try:
                    # 從檔名解析日期 (格式: chroma_backup_YYYY-MM-DD_HH-MM-SS)
                    date_str = folder.replace("chroma_backup_", "")
                    backup_date = datetime.datetime.strptime(date_str, "%Y-%m-%d_%H-%M-%S")
                    
                    # 檢查是否過期
                    if backup_date < cutoff_date:
                        backup_path = os.path.join(backup_dir, folder)
                        
                        # 刪除備份
                        if os.path.isdir(backup_path):
                            shutil.rmtree(backup_path)
                        else:
                            os.remove(backup_path)
                            
                        logger.info(f"已刪除過期備份: {folder}")
                        removed_count += 1
                except Exception as e:
                    logger.error(f"刪除備份 {folder} 時發生錯誤: {e}")
            
            if removed_count > 0:
                logger.info(f"總共刪除了 {removed_count} 個過期備份")
        except Exception as e:
            logger.error(f"清理過期備份時發生錯誤: {e}")
    
    def setup_scheduled_backup(self):
        """設定排程備份"""
        try:
            # 先清除現有排程
            self.stop_scheduled_backup()
            
            # 獲取備份時間
            backup_time = self.config["backup_time"]
            if not backup_time:
                backup_time = "03:00"  # 預設時間
            
            # 獲取備份間隔
            interval = self.config["backup_interval"]
            
            # 設定排程
            if interval == "daily":
                self.scheduled_job = schedule.every().day.at(backup_time).do(self.scheduled_backup_job)
                logger.info(f"已設定每日 {backup_time} 備份")
            elif interval == "weekly":
                self.scheduled_job = schedule.every().monday.at(backup_time).do(self.scheduled_backup_job)
                logger.info(f"已設定每週一 {backup_time} 備份")
            elif interval == "monthly":
                self.scheduled_job = schedule.every().day.at(backup_time).do(self.check_if_first_day_of_month)
                logger.info(f"已設定每月1日 {backup_time} 備份")
            else:
                logger.warning(f"未知的備份間隔: {interval}，使用每日備份")
                self.scheduled_job = schedule.every().day.at(backup_time).do(self.scheduled_backup_job)
            
            # 啟動排程執行緒
            self.scheduler_thread = threading.Thread(target=self.run_scheduler)
            self.scheduler_thread.daemon = True
            self.scheduler_thread.start()
            
            self.status_var.set(f"備份排程已設定: {interval} {backup_time}")
        except Exception as e:
            logger.error(f"設定排程備份時發生錯誤: {e}")
            self.status_var.set("設定排程失敗")
    
    def check_if_first_day_of_month(self):
        """檢查是否為月初第一天，如果是則執行備份"""
        if datetime.datetime.now().day == 1:
            self.scheduled_backup_job()
    
    def run_scheduler(self):
        """運行排程器"""
        while True:
            schedule.run_pending()
            time.sleep(60)  # 每分鐘檢查一次
    
    def scheduled_backup_job(self):
        """排程備份任務"""
        logger.info("開始執行排程備份")
        self.root.after(0, lambda: self.status_var.set("執行排程備份中..."))
        self.perform_backup()
        return schedule.CancelJob  # 不取消任務，讓它繼續執行
    
    def stop_scheduled_backup(self):
        """停止排程備份"""
        schedule.clear()
        logger.info("已停止所有排程備份")
        self.status_var.set("備份排程已停止")
    
    def refresh_backups(self):
        """刷新備份列表"""
        try:
            backup_dir = self.config["backup_dir"]
            if not os.path.exists(backup_dir):
                self.backup_combo['values'] = []
                return
            
            # 獲取所有備份
            backup_folders = [f for f in os.listdir(backup_dir) if f.startswith("chroma_backup_")]
            backup_folders.sort(reverse=True)  # 最新的排前面
            
            # 格式化顯示
            display_values = []
            for folder in backup_folders:
                try:
                    # 從檔名解析日期 (格式: chroma_backup_YYYY-MM-DD_HH-MM-SS)
                    date_str = folder.replace("chroma_backup_", "")
                    backup_date = datetime.datetime.strptime(date_str, "%Y-%m-%d_%H-%M-%S")
                    
                    # 格式化顯示
                    display = f"{backup_date.strftime('%Y-%m-%d %H:%M:%S')} ({folder})"
                    display_values.append(display)
                except Exception:
                    display_values.append(folder)
            
            self.backup_combo['values'] = display_values
            if display_values:
                self.backup_combo.current(0)
        except Exception as e:
            logger.error(f"刷新備份列表時發生錯誤: {e}")
    
    def on_backup_selected(self, event):
        """當選擇備份時觸發"""
        # 自動選擇資料庫類型為備份
        self.db_type_var.set("backup")
    
    def execute_query(self):
        """執行查詢"""
        try:
            # 獲取參數
            db_type = self.db_type_var.get()
            collection_name = self.query_collection_var.get()
            query_text = self.query_text_var.get()
            n_results = int(self.n_results_var.get())
            
            if not collection_name:
                messagebox.showwarning("警告", "請選擇一個集合")
                return
            
            if not query_text:
                messagebox.showwarning("警告", "請輸入查詢文字")
                return
            
            # 確定使用哪個資料庫
            if db_type == "current":
                db_path = self.config["source_db_path"]
                if not db_path:
                    messagebox.showwarning("警告", "請先設定ChromaDB路徑")
                    return
            else:  # backup
                if not self.backup_date_var.get():
                    messagebox.showwarning("警告", "請選擇一個備份")
                    return
                
                # 從顯示文字中提取備份文件夾名稱
                backup_info = self.backup_date_var.get()
                backup_folder = backup_info.split("(")[1].rstrip(")")
                db_path = os.path.join(self.config["backup_dir"], backup_folder)
            
            # 清空結果區域
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, f"查詢中... 資料庫: {db_path}, 集合: {collection_name}\n\n")
            self.root.update()
            
            # 連接資料庫
            client = chromadb.PersistentClient(path=db_path)
            collection = client.get_collection(name=collection_name)
            
            # 執行查詢
            results = collection.query(
                query_texts=[query_text],
                n_results=n_results
            )
            
            # 顯示結果
            self.result_text.delete(1.0, tk.END)
            
            if not results or not results['documents'][0]:
                self.result_text.insert(tk.END, "沒有找到匹配的結果。\n")
                return
                
            # 顯示結果
            documents = results['documents'][0]
            distances = results.get('distances', [[0] * len(documents)])[0]
            metadatas = results.get('metadatas', [[{}] * len(documents)])[0]
            ids = results.get('ids', [[None] * len(documents)])[0]
            
            for i, (doc, dist, meta, doc_id) in enumerate(zip(documents, distances, metadatas, ids)):
                similarity = 1.0 - dist if dist <= 1.0 else 0.0  # 轉換距離為相似度
                
                self.result_text.insert(tk.END, f"--- 結果 #{i+1} ---\n")
                self.result_text.insert(tk.END, f"相似度: {similarity:.4f}\n")
                self.result_text.insert(tk.END, f"ID: {doc_id}\n")
                
                # 顯示元數據
                if meta:
                    self.result_text.insert(tk.END, "元數據:\n")
                    for key, value in meta.items():
                        self.result_text.insert(tk.END, f"  {key}: {value}\n")
                
                # 顯示文本內容
                self.result_text.insert(tk.END, "內容:\n")
                self.result_text.insert(tk.END, f"{doc}\n\n")
            
            logger.info(f"查詢完成，找到 {len(documents)} 個結果")
            self.status_var.set(f"查詢完成，找到 {len(documents)} 個結果")
        except Exception as e:
            error_msg = f"查詢失敗: {e}"
            logger.error(error_msg)
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, f"錯誤: {error_msg}")
            self.status_var.set("查詢失敗")
    
    def refresh_logs(self):
        """刷新日誌顯示"""
        try:
            log_file = "chroma_backup.log"
            if os.path.exists(log_file):
                # 嘗試使用不同的編碼方式讀取日誌
                encodings_to_try = ['utf-8', 'cp950', 'big5', 'gbk', 'latin1']
                logs = None
                
                for encoding in encodings_to_try:
                    try:
                        with open(log_file, 'r', encoding=encoding) as f:
                            logs = f.read()
                        break  # 如果成功讀取，跳出迴圈
                    except UnicodeDecodeError:
                        continue
                
                if logs is not None:
                    self.log_text.delete(1.0, tk.END)
                    self.log_text.insert(tk.END, logs)
                    # 滾動到底部
                    self.log_text.see(tk.END)
                else:
                    # 如果所有編碼都失敗，使用二進制模式讀取並顯示警告
                    with open(log_file, 'rb') as f:
                        binary_data = f.read()
                    self.log_text.delete(1.0, tk.END)
                    self.log_text.insert(tk.END, "警告：無法正確解碼日誌檔案，顯示部分內容：\n\n")
                    # 嘗試使用 latin1（可以映射所有位元組值）
                    self.log_text.insert(tk.END, binary_data.decode('latin1', errors='replace'))
            else:
                self.log_text.delete(1.0, tk.END)
                self.log_text.insert(tk.END, "找不到日誌檔案")
        except Exception as e:
            self.log_text.delete(1.0, tk.END)
            self.log_text.insert(tk.END, f"讀取日誌時發生錯誤: {str(e)}")
        
    def clear_logs(self):
        """清除日誌"""
        if messagebox.askyesno("確認", "確定要清除日誌檔案嗎？"):
            try:
                with open("chroma_backup.log", 'w', encoding='utf-8') as f:
                    f.write("")
                self.log_text.delete(1.0, tk.END)
                self.log_text.insert(tk.END, "日誌已清除")
                logger.info("日誌已被使用者手動清除")
            except Exception as e:
                messagebox.showerror("錯誤", f"清除日誌時發生錯誤: {str(e)}")

def main():
    """程式入口點"""
    root = tk.Tk()
    app = ChromaBackupApp(root)
    
    # 設置圖示 (如果有的話)
    try:
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
        if os.path.exists(icon_path):
            root.iconbitmap(icon_path)
    except Exception:
        pass
    
    # 主循環
    root.mainloop()

if __name__ == "__main__":
    # 啟動應用程式
    main()
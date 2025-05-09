import os
import tkinter as tk
from tkinter import filedialog, messagebox
import json
import chromadb
from chromadb.utils import embedding_functions # 新增導入
import datetime
import pandas as pd
import threading
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.scrolled import ScrolledFrame
import numpy as np
import logging
from typing import List, Dict, Any, Optional, Union, Tuple
import inspect # 用於檢查函數簽名，判斷是否支持混合搜索
import re # 新增導入 for ID parsing in UI

class ChromaDBReader:
    """ChromaDB備份讀取器的主數據模型"""
    
    def __init__(self):
        self.backups_dir = ""
        self.backups = []  # 所有備份的列表
        self.current_backup = None  # 當前選擇的備份
        self.current_collection = None  # 當前選擇的集合
        self.collection_names = []  # 當前備份中的集合列表
        self.query_results = []  # 當前查詢結果
        self.chroma_client = None  # ChromaDB客戶端
        
        self.selected_embedding_model_name = "default"  # 用於查詢的嵌入模型
        self.query_embedding_function = None  # 實例化的查詢嵌入函數, None 表示使用集合內部預設

        # 設置日誌
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler("chroma_reader.log", encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger("ChromaDBReader")
    
    def set_backups_directory(self, directory_path: str) -> bool:
        """設置備份目錄並掃描備份"""
        if not os.path.exists(directory_path):
            self.logger.error(f"備份目錄不存在: {directory_path}")
            return False
        
        self.backups_dir = directory_path
        return self.scan_backups()
    
    def scan_backups(self) -> bool:
        """掃描備份目錄中的所有備份"""
        self.backups = []
        
        try:
            # 查找所有以chroma_backup_開頭的目錄
            for item in os.listdir(self.backups_dir):
                item_path = os.path.join(self.backups_dir, item)
                if os.path.isdir(item_path) and item.startswith("chroma_backup_"):
                    # 提取備份日期時間
                    try:
                        date_str = item.replace("chroma_backup_", "")
                        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d_%H-%M-%S")
                        
                        backup_info = {
                            "name": item,
                            "path": item_path,
                            "date": date_obj,
                            "formatted_date": date_obj.strftime("%Y年%m月%d日 %H:%M:%S")
                        }
                        
                        # 檢查是否是有效的ChromaDB目錄
                        if self._is_valid_chroma_backup(item_path):
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
    
    def _is_valid_chroma_backup(self, backup_path: str) -> bool:
        """檢查目錄是否為有效的ChromaDB備份"""
        # 檢查是否存在關鍵ChromaDB文件
        sqlite_path = os.path.join(backup_path, "chroma.sqlite3")
        return os.path.exists(sqlite_path)
    
    def load_backup(self, backup_index: int) -> bool:
        """加載指定的備份"""
        if backup_index < 0 or backup_index >= len(self.backups):
            self.logger.error(f"無效的備份索引: {backup_index}")
            return False
        
        try:
            self.current_backup = self.backups[backup_index]
            backup_path = self.current_backup["path"]
            
            # 初始化ChromaDB客戶端
            self.chroma_client = chromadb.PersistentClient(path=backup_path)
            
            # 獲取所有集合名稱
            self.collection_names = self.chroma_client.list_collections()
            self.current_collection = None
            self.query_results = []
            
            self.logger.info(f"已加載備份: {self.current_backup['name']}")
            self.logger.info(f"找到 {len(self.collection_names)} 個集合")
            return True
            
        except Exception as e:
            self.logger.error(f"加載備份時出錯: {str(e)}")
            self.current_backup = None
            self.chroma_client = None
            self.collection_names = []
            return False

    def set_query_embedding_model(self, model_name: str):
        """設置查詢時使用的嵌入模型"""
        self.selected_embedding_model_name = model_name
        if model_name == "default":
            self.query_embedding_function = None  # 表示使用集合的內部嵌入函數
            self.logger.info("查詢將使用集合內部嵌入模型。")
        elif model_name == "all-MiniLM-L6-v2":
            try:
                # 注意: sentence-transformers 庫需要安裝
                self.query_embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
                self.logger.info(f"查詢將使用外部嵌入模型: {model_name}")
            except Exception as e:
                self.logger.error(f"無法加載 SentenceTransformer all-MiniLM-L6-v2: {e}。將使用集合內部模型。")
                self.query_embedding_function = None
        elif model_name == "paraphrase-multilingual-MiniLM-L12-v2":
            try:
                # 注意: sentence-transformers 庫需要安裝
                self.query_embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="paraphrase-multilingual-MiniLM-L12-v2")
                self.logger.info(f"查詢將使用外部嵌入模型: {model_name}")
            except Exception as e:
                self.logger.error(f"無法加載 SentenceTransformer paraphrase-multilingual-MiniLM-L12-v2: {e}。將使用集合內部模型。")
                self.query_embedding_function = None
        # 添加新的模型支持
        elif model_name == "paraphrase-multilingual-mpnet-base-v2":
            try:
                # 注意: sentence-transformers 庫需要安裝
                self.query_embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="sentence-transformers/paraphrase-multilingual-mpnet-base-v2")
                self.logger.info(f"查詢將使用外部嵌入模型: {model_name}")
            except Exception as e:
                self.logger.error(f"無法加載 SentenceTransformer paraphrase-multilingual-mpnet-base-v2: {e}。將使用集合內部模型。")
                self.query_embedding_function = None
        else:
            self.logger.warning(f"未知的查詢嵌入模型: {model_name}, 將使用集合內部模型。")
            self.query_embedding_function = None
    
    def load_collection(self, collection_name: str) -> bool:
        """加載指定的集合"""
        if not self.chroma_client or not collection_name:
            return False
        
        try:
            # 獲取集合時，如果需要指定 embedding_function (通常在創建時指定)
            # 此處是讀取，所以集合的 embedding_function 已經固定
            # 我們將在查詢時使用 self.query_embedding_function 來生成 query_embeddings
            self.current_collection = self.chroma_client.get_collection(collection_name)
            self.logger.info(f"已加載集合: {collection_name}")
            return True
        except Exception as e:
            self.logger.error(f"加載集合時出錯: {str(e)}")
            self.current_collection = None
            return False
    
    def execute_query(self, query_text: str, n_results: int = 5, 
                  query_type: str = "basic", 
                  where: Dict = None, 
                  where_document: Dict = None,
                  include: List[str] = None,
                  metadata_filter: Dict = None,
                  hybrid_alpha: float = None) -> List[Dict]:
        """執行查詢並返回結果
    
        參數:
            query_text: 查詢文本
            n_results: 返回結果數量
            query_type: 查詢類型 (basic, metadata, hybrid, multi_vector)
            where: where 過濾條件
            where_document: 文檔內容過濾條件
            include: 指定包含的文檔 ID
            metadata_filter: 元數據過濾條件
            hybrid_alpha: 混合搜索的權重參數（0-1之間，越大越傾向關鍵詞搜索）
        """
        if not self.current_collection or not query_text:
            return []
    
        try:
            query_params = {
                "n_results": n_results
            }
            
            # 基本查詢處理邏輯
            if query_type == "basic":
                query_params["query_texts"] = [query_text]
            # 多向量查詢（用於比較多個查詢之間的相似性）
            elif query_type == "multi_vector":
                # 支持以 "|||" 或換行符分隔的多個查詢文本
                if "|||" in query_text:
                    query_texts = [text.strip() for text in query_text.split("|||")]
                else:
                    query_texts = [text.strip() for text in query_text.splitlines() if text.strip()]
                query_params["query_texts"] = query_texts
            
            # 添加其他查詢參數
            if where:
                query_params["where"] = where
            if where_document:
                query_params["where_document"] = where_document
            if include:
                query_params["include"] = include
            if metadata_filter:
                # 直接將元數據過濾條件轉換為 where 條件
                if "where" not in query_params:
                    query_params["where"] = {}
                query_params["where"].update(metadata_filter)
            
            # 混合搜索處理
            if query_type == "hybrid" and hybrid_alpha is not None:
                # 檢查 ChromaDB 版本是否支持混合搜索
                if hasattr(self.current_collection, "query") and "alpha" in inspect.signature(self.current_collection.query).parameters:
                    query_params["alpha"] = hybrid_alpha
                    # 混合搜索通常需要 query_texts
                    if "query_texts" not in query_params:
                         query_params["query_texts"] = [query_text]
                else:
                    self.logger.warning("當前 ChromaDB 版本不支持混合搜索，將使用基本查詢")
                    query_type = "basic" # 降級為基本查詢
                    query_params["query_texts"] = [query_text]
            elif query_type == "hybrid" and hybrid_alpha is None:
                # 如果是混合搜索但未提供 alpha，則默認為基本搜索
                self.logger.warning("混合搜索未提供 Alpha 值，將使用基本查詢")
                query_type = "basic"
                query_params["query_texts"] = [query_text]


            # 如果 query_type 不是 multi_vector 且 query_texts 未設置，則設置
            if query_type not in ["multi_vector", "hybrid"] and "query_texts" not in query_params:
                 query_params["query_texts"] = [query_text]

            # 如果選擇了外部嵌入模型且不是混合查詢，則生成查詢嵌入
            if query_type != "hybrid" and \
               "query_texts" in query_params and \
               self.query_embedding_function:
                
                texts_to_embed = query_params["query_texts"]
                try:
                    # self.query_embedding_function 接受 List[str] 返回 List[List[float]]
                    generated_embeddings = self.query_embedding_function(texts_to_embed)

                    if generated_embeddings and all(isinstance(emb, list) for emb in generated_embeddings):
                        query_params["query_embeddings"] = generated_embeddings
                        if "query_texts" in query_params: # 確保它存在才刪除
                            del query_params["query_texts"]
                        self.logger.info(f"使用 {self.selected_embedding_model_name} 生成了 {len(generated_embeddings)} 個查詢嵌入。")
                    else:
                        self.logger.warning(f"未能使用 {self.selected_embedding_model_name} 為所有查詢文本生成有效嵌入。將回退到使用集合預設嵌入函數進行文本查詢。嵌入結果: {generated_embeddings}")
                except Exception as e:
                    self.logger.error(f"使用 {self.selected_embedding_model_name} 生成查詢嵌入時出錯: {e}。將回退到使用集合預設嵌入函數進行文本查詢。")

            # 執行查詢
            results = self.current_collection.query(**query_params)
            
            # 處理結果
            processed_results = []
            
            # 獲取查詢返回的所有結果列表
            ids_list = results.get('ids', [[]])
            documents_list = results.get('documents', [[]])
            metadatas_list = results.get('metadatas', [[]])
            distances_list = results.get('distances', [[]])
            
            # 確保列表長度一致，並為空列表提供默認值
            num_queries = len(ids_list)
            if not documents_list or len(documents_list) != num_queries:
                documents_list = [[] for _ in range(num_queries)]
            if not metadatas_list or len(metadatas_list) != num_queries:
                metadatas_list = [[{}] * len(ids_list[i]) for i in range(num_queries)]
            if not distances_list or len(distances_list) != num_queries:
                distances_list = [[0.0] * len(ids_list[i]) for i in range(num_queries)]

            # 對於多查詢文本的情況，需要分別處理每個查詢的結果
            for query_idx, (ids, documents, metadatas, distances) in enumerate(zip(
                ids_list, 
                documents_list,
                metadatas_list,
                distances_list
            )):
                # 處理每個查詢結果
                for i, (doc_id, document, metadata, distance) in enumerate(zip(
                    ids, documents, 
                    metadatas if metadatas else [{}] * len(ids), # 再次確保元數據存在
                    distances if distances else [0.0] * len(ids) # 再次確保距離存在
                )):
                    # 計算相似度分數
                    similarity = 1.0 - min(float(distance) if distance is not None else 1.0, 1.0)
                    
                    result_item = {
                        "rank": i + 1,
                        "query_index": query_idx,
                        "id": doc_id,
                        "document": document,
                        "metadata": metadata if metadata else {}, # 確保 metadata 是字典
                        "similarity": similarity,
                        "distance": float(distance) if distance is not None else 0.0,
                        "query_type": query_type
                    }
                    
                    if query_type == "hybrid":
                        result_item["hybrid_alpha"] = hybrid_alpha
                    
                    processed_results.append(result_item)
            
            self.query_results = processed_results
            self.logger.info(f"查詢完成，找到 {len(processed_results)} 個結果，查詢類型: {query_type}")
            return processed_results
            
        except Exception as e:
            self.logger.error(f"執行查詢時出錯: {str(e)}")
            self.query_results = []
            return []

    def get_documents_by_ids(self, doc_ids: List[str]) -> List[Dict]:
        """按文檔ID列表獲取文檔"""
        if not self.current_collection:
            self.logger.warning("沒有選擇集合，無法按 ID 獲取文檔。")
            return []
        if not doc_ids:
            self.logger.warning("未提供文檔 ID。")
            return []

        try:
            results = self.current_collection.get(
                ids=doc_ids,
                include=["documents", "metadatas"] 
            )
            
            processed_results = []
            retrieved_ids = results.get('ids', [])
            retrieved_documents = results.get('documents', [])
            retrieved_metadatas = results.get('metadatas', [])

            # 創建一個字典以便快速查找已檢索到的文檔信息
            found_docs_map = {}
            for i, r_id in enumerate(retrieved_ids):
                found_docs_map[r_id] = {
                    "document": retrieved_documents[i] if i < len(retrieved_documents) else None,
                    "metadata": retrieved_metadatas[i] if i < len(retrieved_metadatas) else {}
                }

            rank_counter = 1
            for original_id in doc_ids: # 遍歷原始請求的ID，以保持某種順序感，並標記未找到的
                if original_id in found_docs_map:
                    doc_data = found_docs_map[original_id]
                    if doc_data["document"] is not None:
                        processed_results.append({
                            "rank": rank_counter,
                            "id": original_id,
                            "document": doc_data["document"],
                            "metadata": doc_data["metadata"],
                            "similarity": None, # Not applicable
                            "distance": None,   # Not applicable
                            "query_type": "id_lookup" 
                        })
                        rank_counter += 1
                    else: # ID 存在但文檔為空（理論上不應發生在 get 中，除非 include 設置問題）
                        self.logger.warning(f"ID {original_id} 找到但文檔內容為空。")
                # else: # ID 未在返回結果中找到，可以選擇不添加到 processed_results 或添加一個標記
                #    self.logger.info(f"ID {original_id} 未在集合中找到。")
            
            self.query_results = processed_results
            self.logger.info(f"按 ID 查詢完成，從請求的 {len(doc_ids)} 個ID中，實際找到 {len(processed_results)} 個文檔。")
            return processed_results

        except Exception as e:
            self.logger.error(f"按 ID 獲取文檔時出錯: {str(e)}")
            # traceback.print_exc() # For debugging
            self.query_results = []
            return []
    
    def get_collection_info(self, collection_name: str) -> Dict:
        """獲取集合的詳細信息"""
        if not self.chroma_client:
            return {}
        
        try:
            collection = self.chroma_client.get_collection(collection_name)
            count = collection.count()
            
            # 獲取一個樣本來確定向量維度
            sample = collection.peek(1)
            dimension = len(sample['embeddings'][0]) if 'embeddings' in sample and sample['embeddings'] else "未知"
            
            return {
                "name": collection_name,
                "document_count": count,
                "dimension": dimension
            }
        except Exception as e:
            self.logger.error(f"獲取集合信息時出錯: {str(e)}")
            return {
                "name": collection_name,
                "document_count": "未知",
                "dimension": "未知"
            }
    
    def export_results(self, file_path: str, format: str = "csv") -> bool:
        """導出查詢結果"""
        if not self.query_results:
            return False
        
        try:
            df = pd.DataFrame(self.query_results)
            
            # 根據格式導出
            if format.lower() == "csv":
                df.to_csv(file_path, index=False, encoding='utf-8-sig')
            elif format.lower() == "json":
                df.to_json(file_path, orient='records', force_ascii=False, indent=4)
            elif format.lower() == "excel":
                df.to_excel(file_path, index=False)
            else:
                return False
            
            self.logger.info(f"結果已導出到: {file_path}")
            return True
        except Exception as e:
            self.logger.error(f"導出結果時出錯: {str(e)}")
            return False


class ChromaDBReaderUI:
    """ChromaDB備份讀取器的用戶界面"""
    
    def __init__(self, root):
        self.root = root
        self.reader = ChromaDBReader()
        
        # 設置窗口
        self.root.title("ChromaDB 備份讀取器")
        self.root.geometry("1280x800")
        
        # 初始化嵌入模型相關變量
        self.embedding_model_var = tk.StringVar(value="預設 (ChromaDB)") # 顯示名稱
        self.embedding_models = {
            "預設 (ChromaDB)": "default",
            "all-MiniLM-L6-v2 (ST)": "all-MiniLM-L6-v2",
            "paraphrase-multilingual-MiniLM-L12-v2 (ST)": "paraphrase-multilingual-MiniLM-L12-v2",
            "paraphrase-multilingual-mpnet-base-v2 (ST)": "paraphrase-multilingual-mpnet-base-v2"  # 添加新的模型選項
        }
        
        self.setup_ui()
        
        # 默認主題
        self.current_theme = "darkly"  # ttkbootstrap的深色主題
        
        # 存儲配置
        self.config_path = os.path.join(str(Path.home()), ".chroma_reader_config.json")
        self.config = self.load_config()
        
        # 應用保存的配置
        if self.config.get("last_backups_dir"):
            self.backups_dir_var.set(self.config["last_backups_dir"])
            self.load_backups_directory()
    
    def setup_ui(self):
        """設置用戶界面"""
        # 創建主佈局
        self.main_frame = ttk.Frame(self.root, padding=10)
        self.main_frame.pack(fill=BOTH, expand=YES)
        
        # 左側面板 (備份和集合選擇)
        self.left_panel = ttk.Frame(self.main_frame, width=300)
        self.left_panel.pack(side=LEFT, fill=Y, padx=(0, 10))
        
        # 右側面板 (查詢和結果)
        self.right_panel = ttk.Frame(self.main_frame)
        self.right_panel.pack(side=LEFT, fill=BOTH, expand=YES)

        # 設置狀態欄 (提前，以確保 self.status_var 在其他地方使用前已定義)
        self.setup_status_bar()
        
        # 設置左側面板
        self.setup_directory_frame()
        self.setup_embedding_model_frame() # 新增嵌入模型選擇框架
        self.setup_backups_frame()
        self.setup_collections_frame()
        
        # 設置右側面板
        self.setup_query_frame()
        self.setup_results_frame()
        
        # 設置菜單
        self.setup_menu()
    
    def setup_menu(self):
        """設置菜單欄"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # 文件菜單
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="文件", menu=file_menu)
        file_menu.add_command(label="選擇備份目錄", command=self.browse_directory)
        file_menu.add_command(label="刷新備份列表", command=self.refresh_backups)
        file_menu.add_separator()
        file_menu.add_command(label="導出結果...", command=self.export_results_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.root.quit)
        
        # 視圖菜單
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="視圖", menu=view_menu)
        view_menu.add_command(label="切換深色/淺色主題", command=self.toggle_theme)
        
        # 幫助菜單
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="幫助", menu=help_menu)
        help_menu.add_command(label="關於", command=self.show_about)
        help_menu.add_command(label="查看日誌", command=self.open_log_file)
    
    def setup_directory_frame(self):
        """設置目錄選擇框架"""
        dir_frame = ttk.LabelFrame(self.left_panel, text="備份目錄", padding=10)
        dir_frame.pack(fill=X, pady=(0, 10))
        
        self.backups_dir_var = tk.StringVar()
        
        ttk.Entry(dir_frame, textvariable=self.backups_dir_var).pack(side=LEFT, fill=X, expand=YES)
        ttk.Button(dir_frame, text="瀏覽", command=self.browse_directory).pack(side=LEFT, padx=(5, 0))
        ttk.Button(dir_frame, text="載入", command=self.load_backups_directory).pack(side=LEFT, padx=(5, 0))

    def setup_embedding_model_frame(self):
        """設置查詢嵌入模型選擇框架"""
        embedding_frame = ttk.LabelFrame(self.left_panel, text="查詢嵌入模型", padding=10)
        embedding_frame.pack(fill=X, pady=(0, 10))

        self.embedding_model_combo = ttk.Combobox(
            embedding_frame,
            textvariable=self.embedding_model_var,
            values=list(self.embedding_models.keys()),
            state="readonly"
        )
        self.embedding_model_combo.pack(fill=X, expand=YES)
        self.embedding_model_combo.set(list(self.embedding_models.keys())[0]) # 設置預設顯示值
        self.embedding_model_combo.bind("<<ComboboxSelected>>", self.on_embedding_model_changed)

        # 初始化Reader中的嵌入模型選擇
        self.on_embedding_model_changed() 
    
    def setup_backups_frame(self):
        """設置備份列表框架"""
        backups_frame = ttk.LabelFrame(self.left_panel, text="備份列表", padding=10)
        backups_frame.pack(fill=BOTH, expand=YES, pady=(0, 10))
        
        # 備份搜索
        search_frame = ttk.Frame(backups_frame)
        search_frame.pack(fill=X, pady=(0, 5))
        
        self.backup_search_var = tk.StringVar()
        self.backup_search_var.trace("w", self.filter_backups)
        
        ttk.Label(search_frame, text="搜索:").pack(side=LEFT)
        ttk.Entry(search_frame, textvariable=self.backup_search_var).pack(side=LEFT, fill=X, expand=YES)
        
        # 備份列表
        list_frame = ttk.Frame(backups_frame)
        list_frame.pack(fill=BOTH, expand=YES)
        
        columns = ("name", "date")
        self.backups_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=10)
        self.backups_tree.heading("name", text="名稱")
        self.backups_tree.heading("date", text="日期")
        self.backups_tree.column("name", width=100)
        self.backups_tree.column("date", width=150)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=VERTICAL, command=self.backups_tree.yview)
        self.backups_tree.configure(yscrollcommand=scrollbar.set)
        
        self.backups_tree.pack(side=LEFT, fill=BOTH, expand=YES)
        scrollbar.pack(side=LEFT, fill=Y)
        
        self.backups_tree.bind("<<TreeviewSelect>>", self.on_backup_selected)
    
    def setup_collections_frame(self):
        """設置集合列表框架"""
        collections_frame = ttk.LabelFrame(self.left_panel, text="集合列表", padding=10)
        collections_frame.pack(fill=BOTH, expand=YES)
        
        # 集合搜索
        search_frame = ttk.Frame(collections_frame)
        search_frame.pack(fill=X, pady=(0, 5))
        
        self.collection_search_var = tk.StringVar()
        self.collection_search_var.trace("w", self.filter_collections)
        
        ttk.Label(search_frame, text="搜索:").pack(side=LEFT)
        ttk.Entry(search_frame, textvariable=self.collection_search_var).pack(side=LEFT, fill=X, expand=YES)
        
        # 集合列表
        list_frame = ttk.Frame(collections_frame)
        list_frame.pack(fill=BOTH, expand=YES)
        
        columns = ("name", "count")
        self.collections_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=10)
        self.collections_tree.heading("name", text="名稱")
        self.collections_tree.heading("count", text="文檔數")
        self.collections_tree.column("name", width=150)
        self.collections_tree.column("count", width=100)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=VERTICAL, command=self.collections_tree.yview)
        self.collections_tree.configure(yscrollcommand=scrollbar.set)
        
        self.collections_tree.pack(side=LEFT, fill=BOTH, expand=YES)
        scrollbar.pack(side=LEFT, fill=Y)
        
        self.collections_tree.bind("<<TreeviewSelect>>", self.on_collection_selected)
    
    def setup_query_frame(self):
        """設置查詢框架"""
        query_frame = ttk.LabelFrame(self.right_panel, text="查詢", padding=10)
        query_frame.pack(fill=X, pady=(0, 10))
        
        # 創建一個 Notebook 以包含不同的查詢類型標籤頁
        self.query_notebook = ttk.Notebook(query_frame)
        self.query_notebook.pack(fill=X, pady=5)
        
        # 基本查詢標籤頁
        self.basic_query_frame = ttk.Frame(self.query_notebook)
        self.query_notebook.add(self.basic_query_frame, text="基本查詢")
        
        # 元數據查詢標籤頁
        self.metadata_query_frame = ttk.Frame(self.query_notebook)
        self.query_notebook.add(self.metadata_query_frame, text="元數據查詢")
        
        # 混合查詢標籤頁
        self.hybrid_query_frame = ttk.Frame(self.query_notebook)
        self.query_notebook.add(self.hybrid_query_frame, text="混合查詢")
        
        # 多向量查詢標籤頁
        self.multi_vector_frame = ttk.Frame(self.query_notebook)
        self.query_notebook.add(self.multi_vector_frame, text="多向量查詢")

        # ID 查詢標籤頁 (新增)
        self.id_query_frame = ttk.Frame(self.query_notebook)
        self.query_notebook.add(self.id_query_frame, text="ID 查詢")
        
        # 設置基本查詢頁面
        self.setup_basic_query_tab()
        
        # 設置元數據查詢頁面
        self.setup_metadata_query_tab()
        
        # 設置混合查詢頁面
        self.setup_hybrid_query_tab()
        
        # 設置多向量查詢頁面
        self.setup_multi_vector_tab()

        # 設置 ID 查詢頁面 (新增)
        self.setup_id_query_tab()
        
        # 查詢參數（共用部分）
        params_frame = ttk.Frame(query_frame)
        params_frame.pack(fill=X)
        
        ttk.Label(params_frame, text="結果數量:").pack(side=LEFT)
        self.n_results_var = tk.StringVar(value="5")
        ttk.Spinbox(params_frame, from_=1, to=100, textvariable=self.n_results_var, width=5).pack(side=LEFT, padx=(5, 20))
        
        # 查詢按鈕
        ttk.Button(
            query_frame, 
            text="執行查詢", 
            command=self.execute_query, # 注意：這個 execute_query 方法將被新的替換
            style="Accent.TButton"
        ).pack(pady=10)

    def setup_basic_query_tab(self):
        """設置基本查詢標籤頁"""
        ttk.Label(self.basic_query_frame, text="查詢文本:").pack(anchor=W)
        self.basic_query_text = tk.Text(self.basic_query_frame, height=4, width=50)
        self.basic_query_text.pack(fill=X, pady=5)

    def setup_metadata_query_tab(self):
        """設置元數據查詢標籤頁"""
        ttk.Label(self.metadata_query_frame, text="查詢文本:").pack(anchor=W)
        self.metadata_query_text = tk.Text(self.metadata_query_frame, height=4, width=50)
        self.metadata_query_text.pack(fill=X, pady=5)
        
        ttk.Label(self.metadata_query_frame, text="元數據過濾條件 (JSON 格式):").pack(anchor=W)
        self.metadata_filter_text = tk.Text(self.metadata_query_frame, height=4, width=50)
        self.metadata_filter_text.pack(fill=X, pady=5)
        self.metadata_filter_text.insert("1.0", '{"key": "value"}')
        
        # 添加一個幫助按鈕，顯示元數據過濾語法的說明
        ttk.Button(
            self.metadata_query_frame,
            text="?",
            width=2,
            command=self.show_metadata_help
        ).pack(anchor=E)

    def setup_hybrid_query_tab(self):
        """設置混合查詢標籤頁"""
        ttk.Label(self.hybrid_query_frame, text="查詢文本:").pack(anchor=W)
        self.hybrid_query_text = tk.Text(self.hybrid_query_frame, height=4, width=50)
        self.hybrid_query_text.pack(fill=X, pady=5)
        
        alpha_frame = ttk.Frame(self.hybrid_query_frame)
        alpha_frame.pack(fill=X)
        
        ttk.Label(alpha_frame, text="Alpha 值 (0-1):").pack(side=LEFT)
        self.hybrid_alpha_var = tk.DoubleVar(value=0.5)
        ttk.Scale(
            alpha_frame, 
            from_=0.0, to=1.0, 
            variable=self.hybrid_alpha_var, 
            orient=tk.HORIZONTAL,
            length=200
        ).pack(side=LEFT, padx=5, fill=X, expand=YES)
        
        # 創建一個Label來顯示Scale的當前值
        self.hybrid_alpha_label = ttk.Label(alpha_frame, text=f"{self.hybrid_alpha_var.get():.2f}")
        self.hybrid_alpha_label.pack(side=LEFT)
        # 綁定Scale的變動到更新Label的函數
        self.hybrid_alpha_var.trace_add("write", lambda *args: self.hybrid_alpha_label.config(text=f"{self.hybrid_alpha_var.get():.2f}"))

        ttk.Label(self.hybrid_query_frame, text="注意: Alpha=0 完全使用向量搜索，Alpha=1 完全使用關鍵詞搜索").pack(pady=2)
        ttk.Label(self.hybrid_query_frame, text="混合查詢將使用集合原始嵌入模型，忽略上方選擇的查詢嵌入模型。", font=("TkDefaultFont", 8)).pack(pady=2)


    def setup_multi_vector_tab(self):
        """設置多向量查詢標籤頁"""
        ttk.Label(self.multi_vector_frame, text="多個查詢文本 (每行一個，或使用 ||| 分隔):").pack(anchor=W)
        self.multi_vector_text = tk.Text(self.multi_vector_frame, height=6, width=50)
        self.multi_vector_text.pack(fill=X, pady=5)
        self.multi_vector_text.insert("1.0", "查詢文本 1\n|||查詢文本 2\n|||查詢文本 3")
        
        ttk.Label(self.multi_vector_frame, text="用於比較多個查詢之間的相似性").pack(pady=5)

    def setup_id_query_tab(self):
        """設置ID查詢標籤頁"""
        ttk.Label(self.id_query_frame, text="文檔 ID (每行一個，或用逗號/空格分隔):").pack(anchor=tk.W)
        self.id_query_text = tk.Text(self.id_query_frame, height=6, width=50)
        self.id_query_text.pack(fill=tk.X, pady=5)
        self.id_query_text.insert("1.0", "id1\nid2,id3 id4") # 示例
        ttk.Label(self.id_query_frame, text="此查詢將獲取指定ID的文檔，忽略上方“結果數量”設置。").pack(pady=5)


    def show_metadata_help(self):
        """顯示元數據過濾語法說明"""
        help_text = """元數據過濾語法示例:

基本過濾:
{"category": "文章"}  # 精確匹配

範圍過濾:
{"date": {"$gt": "2023-01-01"}}  # 大於
{"date": {"$lt": "2023-12-31"}}  # 小於
{"count": {"$gte": 10}}  # 大於等於
{"count": {"$lte": 100}}  # 小於等於

多條件過濾:
{"$and": [{"category": "文章"}, {"author": "張三"}]}  # AND 條件
{"$or": [{"category": "文章"}, {"category": "新聞"}]}  # OR 條件

注意: 此處語法遵循 ChromaDB 的過濾語法，非標準 JSON 查詢語法。
"""
        messagebox.showinfo("元數據過濾語法說明", help_text)
    
    def setup_results_frame(self):
        """設置結果顯示框架"""
        self.results_notebook = ttk.Notebook(self.right_panel)
        self.results_notebook.pack(fill=BOTH, expand=YES)
        
        # 列表視圖 - 使用標準 Frame 作為容器
        list_frame = ttk.Frame(self.results_notebook)
        self.results_notebook.add(list_frame, text="列表視圖")
        self.list_view = ttk.Frame(list_frame)
        self.list_view.pack(fill=BOTH, expand=YES)
        
        # 詳細視圖 - 使用標準 Frame 作為容器
        detail_frame = ttk.Frame(self.results_notebook)
        self.results_notebook.add(detail_frame, text="詳細視圖")
        self.detail_view = ttk.Frame(detail_frame)
        self.detail_view.pack(fill=BOTH, expand=YES)
        
        # 可視化視圖
        self.visual_view = ttk.Frame(self.results_notebook)
        self.results_notebook.add(self.visual_view, text="可視化")
        
        # 比較視圖
        self.compare_view = ttk.Frame(self.results_notebook)
        self.results_notebook.add(self.compare_view, text="比較視圖")
    
    def setup_status_bar(self):
        """設置狀態欄"""
        status_frame = ttk.Frame(self.root)
        status_frame.pack(side=BOTTOM, fill=X)
        
        self.status_var = tk.StringVar(value="就緒")
        status_label = ttk.Label(status_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=W)
        status_label.pack(fill=X)

    def on_embedding_model_changed(self, event=None):
        """處理查詢嵌入模型選擇變更事件"""
        selected_display_name = self.embedding_model_var.get()
        model_name_key = self.embedding_models.get(selected_display_name, "default")
        
        if hasattr(self, 'reader') and self.reader:
            self.reader.set_query_embedding_model(model_name_key) # 更新Reader中的模型
            
            # 更新狀態欄提示
            if model_name_key == "default":
                self.status_var.set("查詢將使用集合內部嵌入模型。")
            elif self.reader.query_embedding_function: # 檢查模型是否成功加載
                self.status_var.set(f"查詢將使用外部模型: {selected_display_name}")
            else: # 加載失敗
                self.status_var.set(f"模型 {selected_display_name} 加載失敗/無效，將使用集合內部模型。")
        else:
            # Reader尚未初始化，這通常在UI初始化早期發生
            # self.reader.set_query_embedding_model 會在 setup_embedding_model_frame 中首次調用時處理
            pass
    
    def browse_directory(self):
        """瀏覽選擇備份目錄"""
        directory = filedialog.askdirectory(
            title="選擇ChromaDB備份目錄",
            initialdir=self.backups_dir_var.get() or str(Path.home())
        )
        
        if directory:
            self.backups_dir_var.set(directory)
            self.load_backups_directory()
    
    def load_backups_directory(self):
        """加載備份目錄"""
        directory = self.backups_dir_var.get()
        if not directory:
            return
        
        self.status_var.set("正在掃描備份...")
        self.root.update_idletasks()
        
        if self.reader.set_backups_directory(directory):
            self.refresh_backups_list()
            self.status_var.set(f"已找到 {len(self.reader.backups)} 個備份")
            
            # 保存配置
            self.config["last_backups_dir"] = directory
            self.save_config()
        else:
            self.status_var.set("無法掃描備份目錄")
            messagebox.showerror("錯誤", f"無法掃描備份目錄: {directory}")
    
    def refresh_backups(self):
        """刷新備份列表"""
        if not self.reader.backups_dir:
            messagebox.showinfo("提示", "請先選擇備份目錄")
            return
        
        self.status_var.set("正在刷新備份...")
        self.root.update_idletasks()
        
        if self.reader.scan_backups():
            self.refresh_backups_list()
            self.status_var.set(f"已刷新，找到 {len(self.reader.backups)} 個備份")
        else:
            self.status_var.set("刷新備份失敗")
            messagebox.showerror("錯誤", "無法刷新備份列表")
    
    def refresh_backups_list(self):
        """刷新備份列表顯示"""
        # 清空列表
        for item in self.backups_tree.get_children():
            self.backups_tree.delete(item)
        
        # 添加備份
        for backup in self.reader.backups:
            self.backups_tree.insert(
                "", "end",
                values=(backup["name"], backup["formatted_date"])
            )
    
    def filter_backups(self, *args):
        """根據搜索條件過濾備份列表"""
        search_text = self.backup_search_var.get().lower()
        
        # 清空列表
        for item in self.backups_tree.get_children():
            self.backups_tree.delete(item)
        
        # 添加匹配的備份
        for backup in self.reader.backups:
            if search_text in backup["name"].lower() or search_text in backup["formatted_date"].lower():
                self.backups_tree.insert(
                    "", "end",
                    values=(backup["name"], backup["formatted_date"])
                )
    
    def on_backup_selected(self, event):
        """處理備份選擇事件"""
        selection = self.backups_tree.selection()
        if not selection:
            return
        
        # 獲取選定項的索引
        item_id = selection[0]
        # item_index = self.backups_tree.index(item_id) # 這個索引是相對於當前顯示的項目的

        # 直接從 Treeview item 中獲取備份名稱，然後在 self.reader.backups 中查找
        try:
            backup_name_from_tree = self.backups_tree.item(item_id)["values"][0]
        except IndexError:
            self.logger.error("無法從 Treeview 獲取備份名稱")
            return

        actual_backup_index = -1
        for i, backup_info in enumerate(self.reader.backups):
            if backup_info["name"] == backup_name_from_tree:
                actual_backup_index = i
                break
        
        if actual_backup_index == -1:
            self.logger.error(f"在備份列表中未找到名為 {backup_name_from_tree} 的備份")
            return
        
        # 載入備份
        self.status_var.set(f"正在載入備份: {backup_name_from_tree}...")
        self.root.update_idletasks()
        
        # 確保 Reader 中的嵌入模型是最新的 (雖然 on_embedding_model_changed 應該已經處理了)
        # selected_display_name = self.embedding_model_var.get()
        # model_key = self.embedding_models.get(selected_display_name, "default")
        # self.reader.set_query_embedding_model(model_key) # 這行不需要，因為模型選擇是獨立的

        def load_backup_thread():
            # load_backup 不再需要 embedding_model_name 參數，因為嵌入模型選擇是針對查詢的
            success = self.reader.load_backup(actual_backup_index)
            self.root.after(0, lambda: self.finalize_backup_loading(success, backup_name_from_tree))
        
        threading.Thread(target=load_backup_thread).start()
    
    def finalize_backup_loading(self, success: bool, backup_name: str):
        """完成備份載入處理"""
        if success:
            self.refresh_collections_list()
            self.status_var.set(f"已載入備份: {backup_name}")
        else:
            self.status_var.set(f"載入備份失敗: {backup_name}")
            messagebox.showerror("錯誤", f"無法載入備份: {backup_name}")
    
    def refresh_collections_list(self):
        """刷新集合列表顯示"""
        # 清空列表
        for item in self.collections_tree.get_children():
            self.collections_tree.delete(item)
        
        # 添加集合
        for collection in self.reader.collection_names:
            info = self.reader.get_collection_info(collection.name)
            self.collections_tree.insert(
                "", "end",
                values=(collection.name, info["document_count"])
            )
    
    def filter_collections(self, *args):
        """根據搜索條件過濾集合列表"""
        search_text = self.collection_search_var.get().lower()
        
        # 清空列表
        for item in self.collections_tree.get_children():
            self.collections_tree.delete(item)
        
        # 添加匹配的集合
        for collection in self.reader.collection_names:
            if search_text in collection.name.lower():
                info = self.reader.get_collection_info(collection.name)
                self.collections_tree.insert(
                    "", "end",
                    values=(collection.name, info["document_count"])
                )
    
    def on_collection_selected(self, event):
        """處理集合選擇事件"""
        selection = self.collections_tree.selection()
        if not selection:
            return
        
        # 獲取選定項的集合名稱
        item_id = selection[0]
        collection_name = self.collections_tree.item(item_id)["values"][0]
        
        # 載入集合
        self.status_var.set(f"正在載入集合: {collection_name}...")
        self.root.update_idletasks()
        
        def load_collection_thread():
            success = self.reader.load_collection(collection_name)
            self.root.after(0, lambda: self.finalize_collection_loading(success, collection_name))
        
        threading.Thread(target=load_collection_thread).start()
    
    def finalize_collection_loading(self, success: bool, collection_name: str):
        """完成集合載入處理"""
        if success:
            self.status_var.set(f"已載入集合: {collection_name}")
            # 獲取集合詳細信息並顯示
            info = self.reader.get_collection_info(collection_name)
            info_text = f"集合: {info['name']}\n文檔數: {info['document_count']}\n向量維度: {info['dimension']}"
            # messagebox.showinfo("集合信息", info_text) # 暫時註解掉，避免每次選集合都彈窗
        else:
            self.status_var.set(f"載入集合失敗: {collection_name}")
            messagebox.showerror("錯誤", f"無法載入集合: {collection_name}")
    
    def execute_query(self):
        """執行向量查詢"""
        if not self.reader.current_collection:
            messagebox.showinfo("提示", "請先選擇一個集合")
            return
        
        # 根據當前選擇的標籤頁確定查詢類型
        try:
            current_tab_widget = self.query_notebook.nametowidget(self.query_notebook.select())
            if current_tab_widget == self.basic_query_frame:
                current_tab = 0
            elif current_tab_widget == self.metadata_query_frame:
                current_tab = 1
            elif current_tab_widget == self.hybrid_query_frame:
                current_tab = 2
            elif current_tab_widget == self.multi_vector_frame:
                current_tab = 3
            elif current_tab_widget == self.id_query_frame: # 新增 ID 查詢頁判斷
                current_tab = 4
            else:
                messagebox.showerror("錯誤", "未知的查詢標籤頁")
                return
        except tk.TclError: # Notebook可能還沒有任何分頁被選中
             messagebox.showerror("錯誤", "請選擇一個查詢類型標籤頁")
             return

        # 獲取查詢參數
        try:
            n_results = int(self.n_results_var.get())
        except ValueError:
            messagebox.showerror("錯誤", "結果數量必須是整數")
            return
        
        # 執行不同類型的查詢
        if current_tab == 0:  # 基本查詢
            query_text = self.basic_query_text.get("1.0", tk.END).strip()
            if not query_text:
                messagebox.showinfo("提示", "請輸入查詢文本")
                return
            
            self.status_var.set("正在執行基本查詢...")
            self.execute_basic_query(query_text, n_results)
            
        elif current_tab == 1:  # 元數據查詢
            query_text = self.metadata_query_text.get("1.0", tk.END).strip()
            metadata_filter_text = self.metadata_filter_text.get("1.0", tk.END).strip()
            
            if not query_text: # 元數據查詢的文本也可以是空的，如果只想用metadata_filter
                # messagebox.showinfo("提示", "請輸入查詢文本")
                # return
                pass # 允許空查詢文本
            
            try:
                metadata_filter = json.loads(metadata_filter_text) if metadata_filter_text else None
            except json.JSONDecodeError:
                messagebox.showerror("錯誤", "元數據過濾條件必須是有效的 JSON 格式")
                return
            
            if not query_text and not metadata_filter:
                messagebox.showinfo("提示", "請輸入查詢文本或元數據過濾條件")
                return

            self.status_var.set("正在執行元數據查詢...")
            self.execute_metadata_query(query_text, n_results, metadata_filter)
            
        elif current_tab == 2:  # 混合查詢
            query_text = self.hybrid_query_text.get("1.0", tk.END).strip()
            hybrid_alpha = self.hybrid_alpha_var.get()
            
            if not query_text:
                messagebox.showinfo("提示", "請輸入查詢文本")
                return
            
            self.status_var.set("正在執行混合查詢...")
            self.execute_hybrid_query(query_text, n_results, hybrid_alpha)
            
        elif current_tab == 3:  # 多向量查詢
            query_text = self.multi_vector_text.get("1.0", tk.END).strip()
            
            if not query_text:
                messagebox.showinfo("提示", "請輸入查詢文本")
                return
            
            self.status_var.set("正在執行多向量查詢...")
            self.execute_multi_vector_query(query_text, n_results)

        elif current_tab == 4: # ID 查詢
            id_input_str = self.id_query_text.get("1.0", tk.END).strip()
            if not id_input_str:
                messagebox.showinfo("提示", "請輸入文檔 ID。")
                return

            # 解析 ID: 支持逗號、空格、換行符分隔
            doc_ids = [id_val.strip() for id_val in re.split(r'[,\s\n]+', id_input_str) if id_val.strip()]
            
            if not doc_ids:
                messagebox.showinfo("提示", "未解析到有效的文檔 ID。")
                return
            
            self.status_var.set("正在按 ID 獲取文檔...")
            self.execute_id_lookup_query(doc_ids)


    def execute_basic_query(self, query_text, n_results):
        """執行基本查詢"""
        self.status_var.set(f"正在執行基本查詢: {query_text[:30]}...")
        self.root.update_idletasks()
        def query_thread():
            results = self.reader.execute_query(
                query_text=query_text, 
                n_results=n_results,
                query_type="basic"
            )
            self.root.after(0, lambda: self.display_results(results))
        
        threading.Thread(target=query_thread, daemon=True).start()

    def execute_metadata_query(self, query_text, n_results, metadata_filter):
        """執行元數據查詢"""
        self.status_var.set(f"正在執行元數據查詢: {query_text[:30]}...")
        self.root.update_idletasks()
        def query_thread():
            results = self.reader.execute_query(
                query_text=query_text, 
                n_results=n_results,
                query_type="metadata", # 這裡應該是 "metadata" 但後端邏輯會轉為 where
                metadata_filter=metadata_filter
            )
            self.root.after(0, lambda: self.display_results(results))
        
        threading.Thread(target=query_thread, daemon=True).start()

    def execute_hybrid_query(self, query_text, n_results, hybrid_alpha):
        """執行混合查詢"""
        self.status_var.set(f"正在執行混合查詢 (α={hybrid_alpha:.2f}): {query_text[:30]}...")
        self.root.update_idletasks()
        def query_thread():
            results = self.reader.execute_query(
                query_text=query_text, 
                n_results=n_results,
                query_type="hybrid",
                hybrid_alpha=hybrid_alpha
            )
            self.root.after(0, lambda: self.display_results(results))
        
        threading.Thread(target=query_thread, daemon=True).start()

    def execute_multi_vector_query(self, query_text, n_results):
        """執行多向量查詢"""
        self.status_var.set(f"正在執行多向量查詢: {query_text.splitlines()[0][:30] if query_text.splitlines() else ''}...")
        self.root.update_idletasks()
        def query_thread():
            results = self.reader.execute_query(
                query_text=query_text, 
                n_results=n_results,
                query_type="multi_vector"
            )
            self.root.after(0, lambda: self.display_results(results))
        
        threading.Thread(target=query_thread, daemon=True).start()

    def execute_id_lookup_query(self, doc_ids: List[str]):
        """執行ID查找查詢"""
        self.status_var.set(f"正在按 ID 獲取 {len(doc_ids)} 個文檔...")
        self.root.update_idletasks()
        def query_thread():
            results = self.reader.get_documents_by_ids(doc_ids)
            self.root.after(0, lambda: self.display_results(results))
        
        threading.Thread(target=query_thread, daemon=True).start()
    
    def display_results(self, results):
        """顯示查詢結果"""
        if not results:
            self.status_var.set("查詢完成，未找到結果")
            messagebox.showinfo("查詢結果", "未找到匹配的結果")
            return
        
        self.status_var.set(f"查詢完成，找到 {len(results)} 個結果")
        
        # 清空所有視圖 (這部分由各個顯示函數內部處理)
        
        # 顯示列表視圖
        self.display_list_view(results)
        
        # 顯示詳細視圖
        self.display_detail_view(results)
        
        # 顯示可視化視圖
        self.display_visual_view(results)
        
        # 顯示比較視圖
        self.display_compare_view(results)
    
    def display_list_view(self, results):
        """顯示列表視圖"""
        # 清空現有內容
        for widget in self.list_view.winfo_children():
            widget.destroy()
            
        # 創建表格
        columns = ("rank", "similarity", "query_type", "id", "document")
        tree = ttk.Treeview(self.list_view, columns=columns, show="headings")
        tree.heading("rank", text="#")
        tree.heading("similarity", text="相似度")
        tree.heading("query_type", text="查詢類型")
        tree.heading("id", text="文檔ID")
        tree.heading("document", text="文檔內容")
        
        tree.column("rank", width=50, anchor=CENTER)
        tree.column("similarity", width=100, anchor=CENTER)
        tree.column("query_type", width=120, anchor=CENTER) # 調整寬度以適應更長的類型名稱
        tree.column("id", width=150)
        tree.column("document", width=530) # 調整寬度
        
        # 確定查詢類型名稱映射
        query_type_names = {
            "basic": "基本查詢",
            "metadata": "元數據查詢", 
            "hybrid": "混合查詢",
            "multi_vector": "多向量查詢",
            "id_lookup": "ID 查詢" # 新增
        }
        
        # 添加結果到表格
        for result in results:
            raw_query_type = result.get("query_type", "basic")
            display_query_type = query_type_names.get(raw_query_type, raw_query_type.capitalize())

            if raw_query_type == "hybrid" and "hybrid_alpha" in result:
                display_query_type += f" (α={result['hybrid_alpha']:.2f})"
            if raw_query_type == "multi_vector" and "query_index" in result:
                display_query_type += f" (Q{result['query_index']+1})"
            
            similarity_display = f"{result.get('similarity', 0.0):.4f}" if result.get('similarity') is not None else "N/A"
            
            tree.insert(
                "", "end",
                values=(
                    result.get("rank", "-"),
                    similarity_display,
                    display_query_type,
                    result.get("id", "N/A"),
                    result.get("document", "")[:100] + ("..." if len(result.get("document", "")) > 100 else "")
                )
            )
        
        # 添加滾動條
        scrollbar = ttk.Scrollbar(self.list_view, orient=VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        # 雙擊項目顯示完整內容
        tree.bind("<Double-1>", lambda event: self.show_full_document(tree))
        
        # 佈局
        tree.pack(side=LEFT, fill=BOTH, expand=YES)
        scrollbar.pack(side=RIGHT, fill=Y)
    
    def show_full_document(self, tree):
        """顯示完整的文檔內容"""
        selection = tree.selection()
        if not selection:
            return
        
        item_id = selection[0]
        rank_str = tree.item(item_id)["values"][0]
        
        try:
            rank = int(rank_str)
            if 1 <= rank <= len(self.reader.query_results):
                result = self.reader.query_results[rank - 1]
                
                # 創建詳細內容窗口
                details_window = tk.Toplevel(self.root)
                details_window.title(f"文檔詳細內容 - {result['id']}")
                details_window.geometry("800x600")
                
                frame = ttk.Frame(details_window, padding=10)
                frame.pack(fill=BOTH, expand=YES)
                
                # 添加文檔信息
                info_text = f"文檔ID: {result['id']}\n"
                if result.get('similarity') is not None:
                    info_text += f"相似度: {result['similarity']:.4f}\n"
                else:
                    info_text += "相似度: N/A\n"
                
                if result['metadata']:
                    info_text += "\n元數據:\n"
                    for key, value in result['metadata'].items():
                        info_text += f"{key}: {value}\n"
                
                ttk.Label(frame, text=info_text, justify=LEFT).pack(anchor=W, pady=(0, 10))
                
                # 添加文檔內容
                ttk.Label(frame, text="文檔內容:", justify=LEFT).pack(anchor=W)
                
                text_area = tk.Text(frame, wrap=tk.WORD)
                text_area.insert(tk.END, result['document'])
                text_area.config(state=tk.DISABLED)
                
                scrollbar = ttk.Scrollbar(frame, orient=VERTICAL, command=text_area.yview)
                text_area.configure(yscrollcommand=scrollbar.set)
                
                text_area.pack(side=LEFT, fill=BOTH, expand=YES)
                scrollbar.pack(side=LEFT, fill=Y)
                
                # 添加複製按鈕
                ttk.Button(
                    details_window, 
                    text="複製內容", 
                    command=lambda: self.copy_to_clipboard(result['document'])
                ).pack(pady=10)
                
        except (ValueError, IndexError):
            pass
    
    def copy_to_clipboard(self, text):
        """複製文本到剪貼板"""
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_var.set("已複製到剪貼板")
    
    def display_detail_view(self, results):
        """顯示詳細視圖"""
        # 清空現有內容
        for widget in self.detail_view.winfo_children():
            widget.destroy()
            
        # 創建滾動區域
        canvas = tk.Canvas(self.detail_view)
        scrollbar = ttk.Scrollbar(self.detail_view, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # 為每個結果創建一個卡片
        for i, result in enumerate(results):
            # 創建卡片框架
            card = ttk.Frame(scrollable_frame, padding=10, relief="solid", borderwidth=1)
            card.pack(fill=X, padx=10, pady=5, anchor=W)
            
            # 卡片標題
            title_frame = ttk.Frame(card)
            title_frame.pack(fill=X)
            
            similarity_text_detail = f"{result['similarity']:.4f}" if result.get('similarity') is not None else "N/A"
            ttk.Label(
                title_frame, 
                text=f"#{result['rank']} - 相似度: {similarity_text_detail}", 
                font=("TkDefaultFont", 10, "bold")
            ).pack(side=LEFT)
            
            ttk.Label(
                title_frame, 
                text=f"ID: {result['id']}", 
                font=("TkDefaultFont", 8)
            ).pack(side=RIGHT)
            
            ttk.Separator(card, orient=HORIZONTAL).pack(fill=X, pady=5)
            
            # 文檔內容
            content_frame = ttk.Frame(card)
            content_frame.pack(fill=X)
            
            doc_text = tk.Text(content_frame, wrap=tk.WORD, height=4)
            doc_text.insert(tk.END, result['document'])
            doc_text.config(state=tk.DISABLED)
            doc_text.pack(fill=X)
            
            # 如果有元數據，顯示元數據
            if result['metadata'] and len(result['metadata']) > 0:
                ttk.Separator(card, orient=HORIZONTAL).pack(fill=X, pady=5)
                
                metadata_frame = ttk.Frame(card)
                metadata_frame.pack(fill=X)
                
                ttk.Label(
                    metadata_frame, 
                    text="元數據:", 
                    font=("TkDefaultFont", 9)
                ).pack(anchor=W)
                
                for key, value in result['metadata'].items():
                    ttk.Label(
                        metadata_frame, 
                        text=f"{key}: {value}", 
                        font=("TkDefaultFont", 8)
                    ).pack(anchor=W, padx=10)
            
            # 操作按鈕
            button_frame = ttk.Frame(card)
            button_frame.pack(fill=X, pady=(5, 0))
            
            ttk.Button(
                button_frame, 
                text="查看完整內容", 
                command=lambda r=result: self.show_full_document_from_result(r)
            ).pack(side=LEFT, padx=5)
            
            ttk.Button(
                button_frame, 
                text="複製內容", 
                command=lambda d=result['document']: self.copy_to_clipboard(d)
            ).pack(side=LEFT, padx=5)
        
        # 配置滾動區域
        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)
    
    def show_full_document_from_result(self, result):
        """從結果直接顯示完整的文檔內容"""
        # 創建詳細內容窗口
        details_window = tk.Toplevel(self.root)
        details_window.title(f"文檔詳細內容 - {result['id']}")
        details_window.geometry("800x600")
        
        frame = ttk.Frame(details_window, padding=10)
        frame.pack(fill=BOTH, expand=YES)
        
        # 添加文檔信息
        info_text = f"文檔ID: {result['id']}\n"
        if result.get('similarity') is not None:
            info_text += f"相似度: {result['similarity']:.4f}\n"
        else:
            info_text += "相似度: N/A\n"
        
        if result['metadata']:
            info_text += "\n元數據:\n"
            for key, value in result['metadata'].items():
                info_text += f"{key}: {value}\n"
        
        ttk.Label(frame, text=info_text, justify=LEFT).pack(anchor=W, pady=(0, 10))
        
        # 添加文檔內容
        ttk.Label(frame, text="文檔內容:", justify=LEFT).pack(anchor=W)
        
        text_area = tk.Text(frame, wrap=tk.WORD)
        text_area.insert(tk.END, result['document'])
        text_area.config(state=tk.DISABLED)
        
        scrollbar = ttk.Scrollbar(frame, orient=VERTICAL, command=text_area.yview)
        text_area.configure(yscrollcommand=scrollbar.set)
        
        text_area.pack(side=LEFT, fill=BOTH, expand=YES)
        scrollbar.pack(side=LEFT, fill=Y)
        
        # 添加複製按鈕
        ttk.Button(
            details_window, 
            text="複製內容", 
            command=lambda: self.copy_to_clipboard(result['document'])
        ).pack(pady=10)
    
    def display_visual_view(self, results):
        """顯示可視化視圖"""
        # 清空現有內容
        for widget in self.visual_view.winfo_children():
            widget.destroy()
            
        if len(results) == 0:
            return
        
        # 創建框架
        figure_frame = ttk.Frame(self.visual_view)
        figure_frame.pack(fill=BOTH, expand=YES, padx=10, pady=10)
        
        # 創建圖表
        fig = plt.Figure(figsize=(10, 6), dpi=100)
        
        # 相似度柱狀圖
        ax1 = fig.add_subplot(121)
        
        # 提取數據
        ranks = [r["rank"] for r in results]
        similarities = [r["similarity"] for r in results]
        
        # 繪製相似度柱狀圖
        bars = ax1.bar(ranks, similarities, color='skyblue')
        
        # 添加數據標籤
        for bar in bars:
            height = bar.get_height()
            ax1.text(
                bar.get_x() + bar.get_width()/2., 
                height + 0.01,
                f'{height:.3f}', 
                ha='center', va='bottom', 
                rotation=0, 
                fontsize=8
            )
        
        ax1.set_xlabel('排名')
        ax1.set_ylabel('相似度')
        ax1.set_title('查詢結果相似度')
        ax1.set_ylim(0, 1)
        ax1.set_xticks(ranks)
        
        # 相似度曲線圖
        ax2 = fig.add_subplot(122)
        ax2.plot(ranks, similarities, 'o-', color='orange')
        
        # 添加數據標籤
        for i, (x, y) in enumerate(zip(ranks, similarities)):
            ax2.text(x, y + 0.02, f'{y:.3f}', ha='center', va='bottom', fontsize=8)
        
        ax2.set_xlabel('排名')
        ax2.set_ylabel('相似度')
        ax2.set_title('相似度分佈曲線')
        ax2.set_ylim(0, 1)
        ax2.set_xticks(ranks)
        
        # 調整佈局
        fig.tight_layout()
        
        # 將圖表嵌入到 Tkinter 窗口
        canvas = FigureCanvasTkAgg(fig, figure_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=BOTH, expand=YES)
    
    def display_compare_view(self, results):
        """顯示比較視圖"""
        # 清空現有內容
        for widget in self.compare_view.winfo_children():
            widget.destroy()
            
        if len(results) < 2:
            ttk.Label(
                self.compare_view, 
                text="需要至少2個結果才能進行比較", 
                font=("TkDefaultFont", 12)
            ).pack(pady=20)
            return
        
        # 創建比較視圖
        ttk.Label(
            self.compare_view, 
            text="結果比較", 
            font=("TkDefaultFont", 14, "bold")
        ).pack(pady=(10, 20))
        
        # 創建比較表格
        columns = ["特性"] + [f"#{r['rank']}" for r in results]
        
        # 創建框架以包含表格和滾動條
        table_frame = ttk.Frame(self.compare_view)
        table_frame.pack(fill=BOTH, expand=YES, padx=10, pady=10)
        
        tree = ttk.Treeview(table_frame, columns=columns, show="headings")
        
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=100, anchor=CENTER)
        
        # 相似度行
        tree.insert(
            "", "end", 
            values=["相似度"] + [f"{r['similarity']:.4f}" for r in results]
        )
        
        # 文檔ID行
        tree.insert(
            "", "end", 
            values=["文檔ID"] + [r['id'] for r in results]
        )
        
        # 文檔長度行
        tree.insert(
            "", "end", 
            values=["文檔長度"] + [len(r['document']) for r in results]
        )
        
        # 從元數據提取共同鍵
        all_keys = set()
        for result in results:
            if result['metadata']:
                for key in result['metadata'].keys():
                    all_keys.add(key)
        
        # 為每個元數據鍵添加一行
        for key in sorted(all_keys):
            values = ["元數據: " + key]
            for result in results:
                if result['metadata'] and key in result['metadata']:
                    values.append(str(result['metadata'][key]))
                else:
                    values.append("-")
            tree.insert("", "end", values=values)
        
        # 添加垂直滾動條
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        
        # 添加水平滾動條
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=tree.xview)
        tree.configure(xscrollcommand=hsb.set)
        
        # 放置表格和滾動條
        tree.grid(column=0, row=0, sticky='nsew')
        vsb.grid(column=1, row=0, sticky='ns')
        hsb.grid(column=0, row=1, sticky='ew')
        
        # 配置表格框架的網格
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
    
    def export_results_dialog(self):
        """顯示導出結果對話框"""
        if not self.reader.query_results:
            messagebox.showinfo("提示", "沒有可導出的結果")
            return
        
        # 詢問導出格式和文件路徑
        formats = [
            ("CSV 文件", "*.csv"),
            ("JSON 文件", "*.json"),
            ("Excel 文件", "*.xlsx")
        ]
        
        file_path = filedialog.asksaveasfilename(
            title="導出結果",
            filetypes=formats,
            defaultextension=".csv"
        )
        
        if not file_path:
            return
        
        # 確定導出格式
        ext = os.path.splitext(file_path)[1].lower()
        format_map = {
            ".csv": "csv",
            ".json": "json",
            ".xlsx": "excel"
        }
        
        format_type = format_map.get(ext, "csv")
        
        # 執行導出
        success = self.reader.export_results(file_path, format_type)
        
        if success:
            messagebox.showinfo("導出成功", f"結果已成功導出到: {file_path}")
        else:
            messagebox.showerror("導出失敗", "導出結果時發生錯誤")
    
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
        about_text = "ChromaDB 備份讀取器\n\n"
        about_text += "版本: 1.0.0\n\n"
        about_text += "這是一個用於讀取和查詢ChromaDB備份的工具，支持相似度搜索和結果可視化。\n\n"
        about_text += "功能包括:\n"
        about_text += "- 讀取備份目錄\n"
        about_text += "- 查詢集合數據\n"
        about_text += "- 多種視圖顯示結果\n"
        about_text += "- 結果導出\n"
        
        messagebox.showinfo("關於", about_text)
    
    def open_log_file(self):
        """打開日誌文件"""
        log_path = "chroma_reader.log"
        
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
                command=lambda: self.refresh_log_view(text_area)
            ).pack(side=LEFT, padx=5)
            
            ttk.Button(
                button_frame, 
                text="清空日誌", 
                command=lambda: self.clear_log_file(text_area)
            ).pack(side=LEFT, padx=5)
        else:
            messagebox.showinfo("提示", "日誌文件不存在")
    
    def refresh_log_view(self, text_area):
        """刷新日誌查看器內容"""
        log_path = "chroma_reader.log"
        
        if os.path.exists(log_path):
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
    
    def clear_log_file(self, text_area):
        """清空日誌文件"""
        if messagebox.askyesno("確認", "確定要清空日誌文件嗎？"):
            log_path = "chroma_reader.log"
            
            try:
                with open(log_path, "w") as f:
                    f.write("")
                
                text_area.config(state=tk.NORMAL)
                text_area.delete("1.0", tk.END)
                text_area.config(state=tk.DISABLED)
                
                messagebox.showinfo("成功", "日誌文件已清空")
            except Exception as e:
                messagebox.showerror("錯誤", f"清空日誌文件時出錯: {str(e)}")
    
    def load_config(self):
        """載入配置"""
        default_config = {
            "last_backups_dir": "",
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
            self.logger.error(f"保存配置時出錯: {str(e)}")


def main():
    """程序入口點"""
    root = ttk.Window(themename="darkly")
    app = ChromaDBReaderUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
重新嵌入工具 (Reembedding Tool)

這個腳本用於將現有ChromaDB集合中的數據使用新的嵌入模型重新計算向量並儲存。
"""

import os
import sys
import json
import time
import argparse
import shutil
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from tqdm import tqdm  # 進度條

try:
    import chromadb
    from chromadb.utils import embedding_functions
except ImportError:
    print("錯誤: 請先安裝 chromadb: pip install chromadb")
    sys.exit(1)

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    print("錯誤: 請先安裝 sentence-transformers: pip install sentence-transformers")
    sys.exit(1)

# 嘗試導入配置
try:
    import config
except ImportError:
    print("警告: 無法導入config.py，將使用預設設定")
    # 建立最小配置
    class MinimalConfig:
        CHROMA_DATA_DIR = "chroma_data"
        BOT_MEMORY_COLLECTION = "wolfhart_memory"
        CONVERSATIONS_COLLECTION = "wolfhart_memory"
        PROFILES_COLLECTION = "wolfhart_memory"
    config = MinimalConfig()

def parse_args():
    """處理命令行參數"""
    parser = argparse.ArgumentParser(description='ChromaDB 數據重新嵌入工具')
    
    parser.add_argument('--new-model', type=str, 
                        default="sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
                        help='新的嵌入模型名稱 (預設: sentence-transformers/paraphrase-multilingual-mpnet-base-v2)')
    
    parser.add_argument('--collections', type=str, nargs='+',
                        help=f'要處理的集合名稱列表，空白分隔 (預設: 使用配置中的所有集合)')
    
    parser.add_argument('--backup', action='store_true',
                        help='在處理前備份資料庫 (推薦)')
    
    parser.add_argument('--batch-size', type=int, default=100,
                        help='批處理大小 (預設: 100)')
    
    parser.add_argument('--temp-collection-suffix', type=str, default="_temp_new",
                        help='臨時集合的後綴名稱 (預設: _temp_new)')
    
    parser.add_argument('--dry-run', action='store_true',
                        help='模擬執行但不實際修改資料')
    
    parser.add_argument('--confirm-dangerous', action='store_true',
                        help='確認執行危險操作(例如刪除集合)')
    
    return parser.parse_args()

def backup_chroma_directory(chroma_dir: str) -> str:
    """備份ChromaDB數據目錄
    
    Args:
        chroma_dir: ChromaDB數據目錄路徑
        
    Returns:
        備份目錄的路徑
    """
    if not os.path.exists(chroma_dir):
        print(f"錯誤: ChromaDB目錄 '{chroma_dir}' 不存在")
        sys.exit(1)
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = f"{chroma_dir}_backup_{timestamp}"
    
    print(f"備份資料庫從 '{chroma_dir}' 到 '{backup_dir}'...")
    shutil.copytree(chroma_dir, backup_dir)
    print(f"備份完成: {backup_dir}")
    
    return backup_dir

def create_embedding_function(model_name: str):
    """創建嵌入函數
    
    Args:
        model_name: 嵌入模型名稱
        
    Returns:
        嵌入函數對象
    """
    if not model_name:
        print("使用ChromaDB預設嵌入模型")
        return embedding_functions.DefaultEmbeddingFunction()
    
    print(f"正在加載嵌入模型: {model_name}")
    try:
        # 直接使用SentenceTransformerEmbeddingFunction
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        embedding_function = SentenceTransformerEmbeddingFunction(model_name=model_name)
        # 預熱模型
        _ = embedding_function(["."])
        return embedding_function
    except Exception as e:
        print(f"錯誤: 無法加載模型 '{model_name}': {e}")
        print("退回到預設嵌入模型")
        return embedding_functions.DefaultEmbeddingFunction()

def get_collection_names(client, default_collections: List[str]) -> List[str]:
    """獲取所有可用的集合名稱
    
    Args:
        client: ChromaDB客戶端
        default_collections: 預設集合列表
        
    Returns:
        可用的集合名稱列表
    """
    try:
        all_collections = client.list_collections()
        collection_names = [col.name for col in all_collections]
        
        if collection_names:
            return collection_names
        else:
            print("警告: 沒有找到集合，將使用預設集合")
            return default_collections
            
    except Exception as e:
        print(f"獲取集合列表失敗: {e}")
        print("將使用預設集合")
        return default_collections

def fetch_collection_data(client, collection_name: str, batch_size: int = 100) -> Dict[str, Any]:
    """從集合中提取所有數據
    
    Args:
        client: ChromaDB客戶端
        collection_name: 集合名稱
        batch_size: 批處理大小
        
    Returns:
        集合數據字典，包含ids, documents, metadatas
    """
    try:
        collection = client.get_collection(name=collection_name)
        
        # 獲取該集合中的項目總數
        count_result = collection.count()
        if count_result == 0:
            print(f"集合 '{collection_name}' 是空的")
            return {"ids": [], "documents": [], "metadatas": []}
        
        print(f"從集合 '{collection_name}' 中讀取 {count_result} 項數據...")
        
        # 分批獲取數據
        all_ids = []
        all_documents = []
        all_metadatas = []
        
        offset = 0
        with tqdm(total=count_result, desc=f"正在讀取 {collection_name}") as pbar:
            while True:
                # 注意: 使用include參數指定只獲取需要的數據
                batch_result = collection.get(
                    limit=batch_size,
                    offset=offset,
                    include=["documents", "metadatas"]
                )
                
                batch_ids = batch_result.get("ids", [])
                if not batch_ids:
                    break
                    
                all_ids.extend(batch_ids)
                all_documents.extend(batch_result.get("documents", []))
                all_metadatas.extend(batch_result.get("metadatas", []))
                
                offset += len(batch_ids)
                pbar.update(len(batch_ids))
                
                if len(batch_ids) < batch_size:
                    break
        
        return {
            "ids": all_ids,
            "documents": all_documents,
            "metadatas": all_metadatas
        }
        
    except Exception as e:
        print(f"從集合 '{collection_name}' 獲取數據時出錯: {e}")
        return {"ids": [], "documents": [], "metadatas": []}

def create_and_populate_collection(
    client, 
    collection_name: str, 
    data: Dict[str, Any], 
    embedding_func,
    batch_size: int = 100,
    dry_run: bool = False
) -> bool:
    """創建新集合並填充數據
    
    Args:
        client: ChromaDB客戶端
        collection_name: 集合名稱
        data: 要添加的數據 (ids, documents, metadatas)
        embedding_func: 嵌入函數
        batch_size: 批處理大小
        dry_run: 是否只模擬執行
        
    Returns:
        成功返回True，否則返回False
    """
    if dry_run:
        print(f"[模擬] 將創建集合 '{collection_name}' 並添加 {len(data['ids'])} 項數據")
        return True
        
    try:
        # 檢查集合是否已存在
        if collection_name in [col.name for col in client.list_collections()]:
            client.delete_collection(collection_name)
        
        # 創建新集合
        collection = client.create_collection(
            name=collection_name,
            embedding_function=embedding_func
        )
        
        # 如果沒有數據，直接返回
        if not data["ids"]:
            print(f"集合 '{collection_name}' 創建完成，但沒有數據添加")
            return True
            
        # 分批添加數據
        total_items = len(data["ids"])
        with tqdm(total=total_items, desc=f"正在填充 {collection_name}") as pbar:
            for i in range(0, total_items, batch_size):
                end_idx = min(i + batch_size, total_items)
                
                batch_ids = data["ids"][i:end_idx]
                batch_docs = data["documents"][i:end_idx]
                batch_meta = data["metadatas"][i:end_idx]
                
                # 處理可能的None值
                processed_docs = []
                for doc in batch_docs:
                    if doc is None:
                        processed_docs.append("")  # 使用空字符串替代None
                    else:
                        processed_docs.append(doc)
                
                collection.add(
                    ids=batch_ids,
                    documents=processed_docs,
                    metadatas=batch_meta
                )
                
                pbar.update(end_idx - i)
        
        print(f"成功將 {total_items} 項數據添加到集合 '{collection_name}'")
        return True
        
    except Exception as e:
        print(f"創建或填充集合 '{collection_name}' 時出錯: {e}")
        import traceback
        traceback.print_exc()
        return False

def swap_collections(
    client, 
    original_collection: str, 
    temp_collection: str,
    confirm_dangerous: bool = False,
    dry_run: bool = False,
    embedding_func = None  # 添加嵌入函數作為參數
) -> bool:
    """替換集合（刪除原始集合，將臨時集合重命名為原始集合名）
    
    Args:
        client: ChromaDB客戶端
        original_collection: 原始集合名稱
        temp_collection: 臨時集合名稱
        confirm_dangerous: 是否確認危險操作
        dry_run: 是否只模擬執行
        embedding_func: 嵌入函數，用於創建新集合
        
    Returns:
        成功返回True，否則返回False
    """
    if dry_run:
        print(f"[模擬] 將替換集合: 刪除 '{original_collection}'，重命名 '{temp_collection}' 到 '{original_collection}'")
        return True
        
    try:
        # 檢查是否有確認標誌
        if not confirm_dangerous:
            response = input(f"警告: 即將刪除集合 '{original_collection}' 並用 '{temp_collection}' 替換它。確認操作? (y/N): ")
            if response.lower() != 'y':
                print("操作已取消")
                return False
        
        # 檢查兩個集合是否都存在
        all_collections = [col.name for col in client.list_collections()]
        if original_collection not in all_collections:
            print(f"錯誤: 原始集合 '{original_collection}' 不存在")
            return False
            
        if temp_collection not in all_collections:
            print(f"錯誤: 臨時集合 '{temp_collection}' 不存在")
            return False
        
        # 獲取臨時集合的所有數據
        # 在刪除原始集合之前先獲取臨時集合的所有數據
        print(f"獲取臨時集合 '{temp_collection}' 的數據...")
        temp_collection_obj = client.get_collection(temp_collection)
        temp_data = temp_collection_obj.get(include=["documents", "metadatas"])
        
        # 刪除原始集合
        print(f"刪除原始集合 '{original_collection}'...")
        client.delete_collection(original_collection)
        
        # 創建一個同名的新集合（與原始集合同名）
        print(f"創建新集合 '{original_collection}'...")
        
        # 使用傳入的嵌入函數或臨時集合的嵌入函數
        embedding_function = embedding_func or temp_collection_obj._embedding_function
        
        # 創建新的集合
        original_collection_obj = client.create_collection(
            name=original_collection, 
            embedding_function=embedding_function
        )
        
        # 將數據添加到新集合
        if temp_data["ids"]:
            print(f"將 {len(temp_data['ids'])} 項數據從臨時集合複製到新集合...")
            
            # 處理可能的None值
            processed_docs = []
            for doc in temp_data["documents"]:
                if doc is None:
                    processed_docs.append("")
                else:
                    processed_docs.append(doc)
            
            # 使用分批方式添加數據以避免潛在的大數據問題
            batch_size = 100
            for i in range(0, len(temp_data["ids"]), batch_size):
                end = min(i + batch_size, len(temp_data["ids"]))
                original_collection_obj.add(
                    ids=temp_data["ids"][i:end],
                    documents=processed_docs[i:end],
                    metadatas=temp_data["metadatas"][i:end] if temp_data["metadatas"] else None
                )
        
        # 刪除臨時集合
        print(f"刪除臨時集合 '{temp_collection}'...")
        client.delete_collection(temp_collection)
        
        print(f"成功用重新嵌入的數據替換集合 '{original_collection}'")
        return True
        
    except Exception as e:
        print(f"替換集合時出錯: {e}")
        import traceback
        traceback.print_exc()
        return False

def process_collection(
    client,
    collection_name: str,
    embedding_func,
    temp_suffix: str,
    batch_size: int,
    confirm_dangerous: bool,
    dry_run: bool
) -> bool:
    """處理一個集合的完整流程
    
    Args:
        client: ChromaDB客戶端
        collection_name: 要處理的集合名稱
        embedding_func: 新的嵌入函數
        temp_suffix: 臨時集合的後綴
        batch_size: 批處理大小
        confirm_dangerous: 是否確認危險操作
        dry_run: 是否只模擬執行
        
    Returns:
        處理成功返回True，否則返回False
    """
    print(f"\n{'=' * 60}")
    print(f"處理集合: '{collection_name}'")
    print(f"{'=' * 60}")
    
    # 暫時集合名稱
    temp_collection_name = f"{collection_name}{temp_suffix}"
    
    # 1. 獲取原始集合的數據
    data = fetch_collection_data(client, collection_name, batch_size)
    
    if not data["ids"]:
        print(f"集合 '{collection_name}' 為空或不存在，跳過")
        return True
    
    # 2. 創建臨時集合並使用新的嵌入模型填充數據
    success = create_and_populate_collection(
        client, 
        temp_collection_name, 
        data, 
        embedding_func,
        batch_size,
        dry_run
    )
    
    if not success:
        print(f"創建臨時集合 '{temp_collection_name}' 失敗，跳過替換")
        return False
    
    # 3. 替換原始集合
    success = swap_collections(
        client, 
        collection_name, 
        temp_collection_name,
        confirm_dangerous,
        dry_run,
        embedding_func  # 添加嵌入函數作為參數
    )
    
    return success

def main():
    """主函數"""
    args = parse_args()
    
    # 獲取ChromaDB目錄
    chroma_dir = getattr(config, "CHROMA_DATA_DIR", "chroma_data")
    print(f"使用ChromaDB目錄: {chroma_dir}")
    
    # 備份數據庫（如果請求）
    if args.backup:
        backup_chroma_directory(chroma_dir)
    
    # 創建ChromaDB客戶端
    try:
        client = chromadb.PersistentClient(path=chroma_dir)
    except Exception as e:
        print(f"錯誤: 無法連接到ChromaDB: {e}")
        sys.exit(1)
    
    # 創建嵌入函數
    embedding_func = create_embedding_function(args.new_model)
    
    # 確定要處理的集合
    if args.collections:
        collections_to_process = args.collections
    else:
        # 使用配置中的默認集合或獲取所有可用集合
        default_collections = [
            getattr(config, "BOT_MEMORY_COLLECTION", "wolfhart_memory"),
            getattr(config, "CONVERSATIONS_COLLECTION", "conversations"),
            getattr(config, "PROFILES_COLLECTION", "user_profiles")
        ]
        collections_to_process = get_collection_names(client, default_collections)
    
    # 過濾掉已經是臨時集合的集合名稱
    filtered_collections = []
    for collection in collections_to_process:
        if args.temp_collection_suffix in collection:
            print(f"警告: 跳過可能的臨時集合 '{collection}'")
            continue
        filtered_collections.append(collection)
    
    collections_to_process = filtered_collections
    
    if not collections_to_process:
        print("沒有找到可處理的集合。")
        sys.exit(0)
    
    print(f"將處理以下集合: {', '.join(collections_to_process)}")
    if args.dry_run:
        print("注意: 執行為乾運行模式，不會實際修改數據")
    
    # 詢問用戶確認
    if not args.confirm_dangerous and not args.dry_run:
        confirm = input("這個操作將使用新的嵌入模型重新計算所有數據。繼續? (y/N): ")
        if confirm.lower() != 'y':
            print("操作已取消")
            sys.exit(0)
    
    # 處理每個集合
    start_time = time.time()
    success_count = 0
    
    for collection_name in collections_to_process:
        if process_collection(
            client,
            collection_name,
            embedding_func,
            args.temp_collection_suffix,
            args.batch_size,
            args.confirm_dangerous,
            args.dry_run
        ):
            success_count += 1
    
    # 報告結果
    elapsed_time = time.time() - start_time
    print(f"\n{'=' * 60}")
    print(f"處理完成: {success_count}/{len(collections_to_process)} 個集合成功")
    print(f"總耗時: {elapsed_time:.2f} 秒")
    print(f"{'=' * 60}")

if __name__ == "__main__":
    main()
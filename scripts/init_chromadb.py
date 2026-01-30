#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ChromaDB 初始化腳本
Initialize ChromaDB database and create initial collection with test data

此腳本用於首次安裝時初始化 ChromaDB，避免 main.py 啟動時出現錯誤
This script initializes ChromaDB on first installation to prevent errors when starting main.py
"""

import os
import sys
import chromadb
from chromadb.utils import embedding_functions

# 設定資料庫路徑 (相對於專案根目錄)
# Set database path (relative to project root)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
CHROMA_DATA_DIR = os.path.join(PROJECT_ROOT, "chroma_data")

# Collection 名稱
# Collection name
COLLECTION_NAME = "wolfhart_memory"

# Embedding 模型
# Embedding model
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"

def init_chromadb():
    """
    初始化 ChromaDB 資料庫並建立初始集合
    Initialize ChromaDB database and create initial collection
    """
    print("="*60)
    print("ChromaDB Initialization Script")
    print("ChromaDB 初始化腳本")
    print("="*60)

    # 建立資料目錄
    # Create data directory
    try:
        os.makedirs(CHROMA_DATA_DIR, exist_ok=True)
        print(f"\n[OK] Created data directory: {CHROMA_DATA_DIR}")
        print(f"[OK] 建立資料目錄: {CHROMA_DATA_DIR}")
    except Exception as e:
        print(f"\n[ERROR] Failed to create data directory: {e}")
        print(f"[ERROR] 無法建立資料目錄: {e}")
        return False

    # 初始化 ChromaDB 客戶端
    # Initialize ChromaDB client
    try:
        client = chromadb.PersistentClient(path=CHROMA_DATA_DIR)
        print(f"[OK] Connected to ChromaDB")
        print(f"[OK] 已連接到 ChromaDB")
    except Exception as e:
        print(f"[ERROR] Failed to connect to ChromaDB: {e}")
        print(f"[ERROR] 無法連接到 ChromaDB: {e}")
        return False

    # 建立 embedding 函數
    # Create embedding function
    try:
        print(f"\n[INFO] Loading embedding model: {EMBEDDING_MODEL}")
        print(f"[INFO] 正在載入 Embedding 模型: {EMBEDDING_MODEL}")
        print(f"[INFO] This may take a while on first run as the model needs to be downloaded...")
        print(f"[INFO] 首次執行時需要下載模型，可能需要一些時間...")

        embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBEDDING_MODEL
        )
        print(f"[OK] Loaded embedding model successfully")
        print(f"[OK] 已成功載入 Embedding 模型")
    except Exception as e:
        print(f"[ERROR] Failed to load embedding model: {e}")
        print(f"[ERROR] 無法載入 Embedding 模型: {e}")
        print(f"\n[HINT] Make sure 'sentence-transformers' is installed:")
        print(f"[HINT] 請確保已安裝 'sentence-transformers'：")
        print(f"       pip install sentence-transformers")
        return False

    # 建立或取得集合
    # Create or get collection
    try:
        collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=embedding_function
        )
        print(f"\n[OK] Created/Retrieved collection: {COLLECTION_NAME}")
        print(f"[OK] 已建立/取得集合: {COLLECTION_NAME}")
    except Exception as e:
        print(f"[ERROR] Failed to create collection: {e}")
        print(f"[ERROR] 無法建立集合: {e}")
        return False

    # 寫入初始測試資料
    # Insert initial test data
    try:
        # 檢查集合是否已有資料
        # Check if collection already has data
        count = collection.count()
        if count > 0:
            print(f"\n[INFO] Collection already contains {count} documents, skipping initialization")
            print(f"[INFO] 集合已存在 {count} 筆資料，跳過初始化")
        else:
            print(f"\n[INFO] Inserting test data...")
            print(f"[INFO] 正在寫入測試資料...")

            # 寫入測試資料
            # Insert test data
            collection.add(
                documents=[
                    "Hello World! This is the initial test document for Wolf Chat ChromaDB initialization. "
                    "你好世界！這是 Wolf Chat ChromaDB 初始化的測試文件。"
                ],
                metadatas=[{
                    "type": "system_init",
                    "purpose": "Initial test document to ensure ChromaDB is properly configured",
                    "created_by": "init_chromadb.py",
                    "language": "en-zh-TW"
                }],
                ids=["init_test_doc_001"]
            )
            print(f"[OK] Inserted test data successfully")
            print(f"[OK] 已成功寫入測試資料")
            print(f"    - Document ID: init_test_doc_001")
            print(f"    - Content: Hello World test message")
    except Exception as e:
        print(f"[ERROR] Failed to insert test data: {e}")
        print(f"[ERROR] 無法寫入測試資料: {e}")
        return False

    # 驗證資料
    # Verify data
    try:
        final_count = collection.count()
        print(f"\n[OK] Verification complete")
        print(f"[OK] 驗證完成")
        print(f"    - Collection: {COLLECTION_NAME}")
        print(f"    - 集合名稱: {COLLECTION_NAME}")
        print(f"    - Document count: {final_count}")
        print(f"    - 文件數量: {final_count}")
        print(f"    - Data directory: {CHROMA_DATA_DIR}")
        print(f"    - 資料目錄: {CHROMA_DATA_DIR}")
    except Exception as e:
        print(f"[WARNING] Failed to verify data: {e}")
        print(f"[WARNING] 無法驗證資料: {e}")

    print("\n" + "="*60)
    print("[SUCCESS] ChromaDB initialization completed!")
    print("[SUCCESS] ChromaDB 初始化完成！")
    print("="*60)
    print("\nYou can now run Setup.py to configure the application.")
    print("現在可以執行 Setup.py 來配置應用程式。")
    print("="*60)
    return True

if __name__ == "__main__":
    try:
        success = init_chromadb()
        if success:
            print("\n[INFO] Press any key to exit...")
            print("[INFO] 按任意鍵退出...")
            input()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n[INFO] User interrupted")
        print("[INFO] 使用者中斷")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n[ERROR] Unexpected error: {e}")
        print(f"[ERROR] 發生未預期的錯誤: {e}")
        import traceback
        traceback.print_exc()
        print("\n[INFO] Press any key to exit...")
        print("[INFO] 按任意鍵退出...")
        input()
        sys.exit(1)

#!/usr/bin/env python3
"""
Last War Manual ChromaDB Import Script
導入Last War手冊到ChromaDB的腳本
"""

import json
import chromadb
from chromadb.utils import embedding_functions
from typing import List, Dict
import sys
from pathlib import Path
import os

# 添加主目錄到Python路徑以導入config
sys.path.insert(0, str(Path(__file__).parent.parent))
import config

class LastWarChromaDBImporter:
    def __init__(self, chroma_data_dir: str = None):
        """初始化ChromaDB客戶端"""
        self.chroma_data_dir = Path(chroma_data_dir or config.CHROMA_DATA_DIR)
        self.client = None
        self.collection = None
        self.embedding_function = None
    
    def get_embedding_function(self):
        """從config獲取嵌入函數，與chroma_client.py保持一致"""
        if self.embedding_function is None:
            model_name = getattr(config, 'EMBEDDING_MODEL_NAME', "sentence-transformers/paraphrase-multilingual-mpnet-base-v2")
            try:
                self.embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=model_name)
                print(f"Successfully initialized embedding function with model: {model_name}")
            except Exception as e:
                print(f"Failed to initialize embedding function with model '{model_name}': {e}")
                # Fallback to default if specified model fails and it's not already the default
                if model_name != "sentence-transformers/paraphrase-multilingual-mpnet-base-v2":
                    print("Falling back to default embedding model: sentence-transformers/paraphrase-multilingual-mpnet-base-v2")
                    try:
                        self.embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
                            model_name="sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
                        )
                        print(f"Successfully initialized embedding function with default model.")
                    except Exception as e_default:
                        print(f"Failed to initialize default embedding function: {e_default}")
                        self.embedding_function = None
                else:
                    self.embedding_function = None
        return self.embedding_function
        
    def connect_to_chromadb(self) -> bool:
        """連接到ChromaDB"""
        try:
            self.client = chromadb.PersistentClient(path=str(self.chroma_data_dir))
            print(f"已連接到ChromaDB: {self.chroma_data_dir}")
            return True
        except Exception as e:
            print(f"連接ChromaDB失敗: {e}")
            return False
    
    def create_or_get_collection(self, collection_name: str = "lastwar_manual") -> bool:
        """創建或獲取collection"""
        try:
            # 獲取embedding function
            emb_func = self.get_embedding_function()
            if emb_func is None:
                print(f"Failed to get or create collection '{collection_name}' due to embedding function initialization failure.")
                return False
            
            # 檢查collection是否已存在
            existing_collections = [col.name for col in self.client.list_collections()]
            
            if collection_name in existing_collections:
                print(f"Collection '{collection_name}' 已存在，將使用現有collection")
                self.collection = self.client.get_collection(collection_name)
                
                # 顯示現有數據統計
                count = self.collection.count()
                if count > 0:
                    response = input(f"現有collection包含 {count} 條記錄。是否清空並重新導入？ (y/N): ")
                    if response.lower() == 'y':
                        self.client.delete_collection(collection_name)
                        self.collection = self.client.create_collection(
                            name=collection_name,
                            embedding_function=emb_func,
                            metadata={
                                "description": "Last War: Survival game manual knowledge base",
                                "source": "Last War manual.md",
                                "created_by": "lastwar_chromadb_importer.py",
                                "embedding_model": getattr(config, 'EMBEDDING_MODEL_NAME', "default")
                            }
                        )
                        print(f"已清空並重新創建collection: {collection_name}")
                    else:
                        print("將向現有collection添加新數據")
            else:
                self.collection = self.client.create_collection(
                    name=collection_name,
                    embedding_function=emb_func,
                    metadata={
                        "description": "Last War: Survival game manual knowledge base",
                        "source": "Last War manual.md", 
                        "created_by": "lastwar_chromadb_importer.py",
                        "embedding_model": getattr(config, 'EMBEDDING_MODEL_NAME', "default")
                    }
                )
                print(f"已創建新collection: {collection_name}")
            
            return True
        except Exception as e:
            print(f"創建/獲取collection失敗: {e}")
            return False
    
    def load_chunks_from_json(self, json_path: str) -> List[Dict]:
        """從JSON文件載入chunks"""
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                chunks = json.load(f)
            print(f"已從 {json_path} 載入 {len(chunks)} 個chunks")
            return chunks
        except Exception as e:
            print(f"載入JSON文件失敗: {e}")
            return []
    
    def import_chunks(self, chunks: List[Dict]) -> bool:
        """導入chunks到ChromaDB"""
        if not chunks:
            print("沒有chunks需要導入")
            return False
        
        try:
            # 準備數據
            ids = []
            documents = []
            metadatas = []
            
            for chunk in chunks:
                ids.append(chunk["id"])
                documents.append(chunk["content"])
                
                # 處理metadata - ChromaDB要求所有值都是字符串
                metadata = {}
                for key, value in chunk["metadata"].items():
                    if value is None:
                        metadata[key] = ""
                    else:
                        metadata[key] = str(value)
                metadatas.append(metadata)
            
            # 批量導入
            batch_size = 100  # ChromaDB推薦的批次大小
            total_batches = (len(chunks) + batch_size - 1) // batch_size
            
            for i in range(0, len(chunks), batch_size):
                batch_end = min(i + batch_size, len(chunks))
                batch_num = i // batch_size + 1
                
                print(f"導入批次 {batch_num}/{total_batches} ({i+1}-{batch_end})")
                
                self.collection.add(
                    ids=ids[i:batch_end],
                    documents=documents[i:batch_end],
                    metadatas=metadatas[i:batch_end]
                )
            
            print(f"成功導入 {len(chunks)} 個chunks到ChromaDB")
            return True
            
        except Exception as e:
            print(f"導入chunks失敗: {e}")
            return False
    
    def verify_import(self) -> bool:
        """驗證導入結果"""
        try:
            count = self.collection.count()
            print(f"Collection中共有 {count} 條記錄")
            
            # 測試查詢
            test_results = self.collection.query(
                query_texts=["hero skills"],
                n_results=3
            )
            
            print(f"\n測試查詢 'hero skills' 結果:")
            for i, (doc, metadata) in enumerate(zip(test_results['documents'][0], test_results['metadatas'][0])):
                print(f"  {i+1}. Part {metadata['part_number']}.{metadata['section_number']}: {metadata['section_title']}")
                print(f"     內容預覽: {doc[:100]}...")
            
            return True
        except Exception as e:
            print(f"驗證導入失敗: {e}")
            return False
    
    def get_collection_stats(self) -> Dict:
        """獲取collection統計信息"""
        try:
            count = self.collection.count()
            
            # 按part統計
            all_data = self.collection.get()
            part_stats = {}
            content_type_stats = {}
            
            for metadata in all_data['metadatas']:
                part_num = metadata.get('part_number', 'unknown')
                part_title = metadata.get('part_title', 'unknown')
                content_type = metadata.get('content_type', 'unknown')
                
                if part_num not in part_stats:
                    part_stats[part_num] = {'title': part_title, 'count': 0}
                part_stats[part_num]['count'] += 1
                
                content_type_stats[content_type] = content_type_stats.get(content_type, 0) + 1
            
            return {
                'total_documents': count,
                'parts': part_stats,
                'content_types': content_type_stats
            }
        except Exception as e:
            print(f"獲取統計信息失敗: {e}")
            return {}

def main():
    """主函數"""
    print("=== Last War Manual ChromaDB 導入工具 ===\n")
    
    # 設置路徑
    json_path = "Z:/coding/dandan2_test/lastwar_manual_chunks.json"
    collection_name = "lastwar_manual"
    
    # 檢查JSON文件是否存在
    if not Path(json_path).exists():
        print(f"錯誤: JSON文件不存在: {json_path}")
        print("請先運行 lastwar_manual_processor.py 生成chunks文件")
        return
    
    # 初始化導入器（使用config中的路徑）
    importer = LastWarChromaDBImporter()
    
    # 連接ChromaDB
    if not importer.connect_to_chromadb():
        return
    
    # 創建或獲取collection
    if not importer.create_or_get_collection(collection_name):
        return
    
    # 載入chunks
    chunks = importer.load_chunks_from_json(json_path)
    if not chunks:
        return
    
    # 導入chunks
    if not importer.import_chunks(chunks):
        return
    
    # 驗證導入
    if not importer.verify_import():
        return
    
    # 顯示統計信息
    stats = importer.get_collection_stats()
    if stats:
        print(f"\n=== 導入完成統計 ===")
        print(f"總文檔數: {stats['total_documents']}")
        print(f"\n各部分文檔數:")
        for part_num, info in sorted(stats['parts'].items()):
            print(f"  Part {part_num}: {info['title']} - {info['count']} 個文檔")
        print(f"\n內容類型分布:")
        for content_type, count in stats['content_types'].items():
            print(f"  {content_type}: {count} 個文檔")
    
    print(f"\n✅ Last War手冊已成功導入到ChromaDB collection: {collection_name}")
    print(f"現在可以在聊天機器人中使用semantic查詢功能了！")

if __name__ == "__main__":
    main()
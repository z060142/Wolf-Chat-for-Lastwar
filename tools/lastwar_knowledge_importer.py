#!/usr/bin/env python3
"""
Last War Knowledge Base Importer - 一鍵導入工具
將Last War手冊處理並導入ChromaDB的完整工具
"""

import os
import sys
from pathlib import Path

# 添加當前目錄到Python路徑  
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from lastwar_manual_processor import LastWarManualProcessor
from lastwar_chromadb_importer import LastWarChromaDBImporter
import config

def main():
    """主函數 - 完整的處理和導入流程"""
    print("=== Last War Knowledge Base 一鍵導入工具 ===\n")
    
    # 自動檢測工作目錄
    base_dir = Path(__file__).parent.parent
    manual_path = base_dir / "Last War manual.md"
    chunks_json_path = base_dir / "lastwar_manual_chunks.json"
    chroma_data_dir = Path(config.CHROMA_DATA_DIR)
    collection_name = "lastwar_manual"
    
    # 檢查源文件
    if not manual_path.exists():
        print(f"❌ 錯誤: 找不到源文件 {manual_path}")
        return False
    
    print(f"📁 源文件: {manual_path}")
    print(f"📄 輸出JSON: {chunks_json_path}")
    print(f"🗄️  ChromaDB目錄: {chroma_data_dir}")
    print(f"📚 Collection名稱: {collection_name}\n")
    
    # 步驟1: 處理文檔
    print("🔄 步驟1: 處理文檔並生成chunks...")
    try:
        processor = LastWarManualProcessor(str(manual_path))
        processor.load_document()
        chunks = processor.process_document()
        
        if not chunks:
            print("❌ 沒有生成任何chunks")
            return False
        
        processor.save_chunks_to_json(str(chunks_json_path))
        
        # 顯示處理統計
        stats = processor.get_statistics()
        print(f"✅ 文檔處理完成:")
        print(f"   - 總chunks: {stats['total_chunks']}")
        print(f"   - 總長度: {stats['total_content_length']:,} 字符")
        print(f"   - 覆蓋部分: {len(stats['parts'])} 個")
        print(f"   - 內容類型: {', '.join(stats['content_types'].keys())}")
        
    except Exception as e:
        print(f"❌ 文檔處理失敗: {e}")
        return False
    
    # 步驟2: 導入ChromaDB
    print(f"\n🔄 步驟2: 導入到ChromaDB...")
    try:
        importer = LastWarChromaDBImporter()  # 使用config中的路徑
        
        # 連接ChromaDB
        if not importer.connect_to_chromadb():
            return False
        
        # 創建collection
        if not importer.create_or_get_collection(collection_name):
            return False
        
        # 載入和導入chunks
        chunks_data = importer.load_chunks_from_json(str(chunks_json_path))
        if not importer.import_chunks(chunks_data):
            return False
        
        # 驗證導入
        if not importer.verify_import():
            return False
        
        # 顯示最終統計
        final_stats = importer.get_collection_stats()
        if final_stats:
            print(f"\n✅ ChromaDB導入完成:")
            print(f"   - Collection: {collection_name}")
            print(f"   - 總文檔數: {final_stats['total_documents']}")
            print(f"   - 覆蓋遊戲部分: {len(final_stats['parts'])} 個")
            
    except Exception as e:
        print(f"❌ ChromaDB導入失敗: {e}")
        return False
    
    # 清理臨時文件
    cleanup = input(f"\n🗑️  是否刪除臨時JSON文件? (y/N): ")
    if cleanup.lower() == 'y':
        try:
            chunks_json_path.unlink()
            print(f"✅ 已刪除臨時文件: {chunks_json_path}")
        except Exception as e:
            print(f"⚠️  刪除臨時文件失敗: {e}")
    
    print(f"\n🎉 Last War知識庫導入完成!")
    print(f"現在可以在聊天機器人中使用以下查詢類型:")
    print(f"   - 遊戲基礎概念查詢")
    print(f"   - 建築和資源管理")
    print(f"   - 英雄和戰鬥系統")
    print(f"   - 聯盟系統和社交功能")
    print(f"   - 日常活動和競賽事件")
    print(f"   - 季節性內容和高級玩法")
    print(f"   - 經濟系統和充值策略")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
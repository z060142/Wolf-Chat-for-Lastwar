#!/usr/bin/env python3
"""
Last War Manual Processing Script for ChromaDB Import
處理Last War手冊並準備ChromaDB導入的腳本
"""

import re
import json
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from pathlib import Path

@dataclass
class DocumentChunk:
    """文檔塊數據結構"""
    content: str
    metadata: Dict[str, str]
    chunk_id: str

class LastWarManualProcessor:
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.lines = []
        self.chunks = []
        
    def load_document(self) -> None:
        """載入文檔"""
        with open(self.file_path, 'r', encoding='utf-8') as f:
            self.lines = f.readlines()
        print(f"已載入文檔，共 {len(self.lines)} 行")
    
    def _extract_part_info(self, line: str) -> Optional[Tuple[str, str]]:
        """提取部分信息 (Part X: Title)"""
        match = re.match(r'## \*\*Part (\d+): (.+?)\*\*', line.strip())
        if match:
            return match.group(1), match.group(2)
        return None
    
    def _extract_section_info(self, line: str) -> Optional[Tuple[str, str]]:
        """提取章節信息 (### **X.X. Title**)"""
        match = re.match(r'### \*\*(\d+\.\d+\.?) (.+?)\*\*', line.strip())
        if match:
            return match.group(1), match.group(2)
        return None
    
    def _is_table_line(self, line: str) -> bool:
        """判斷是否為表格行"""
        return '|' in line.strip() and line.strip().startswith('|')
    
    def _clean_content(self, content: str) -> str:
        """清理內容格式"""
        # 移除行號前綴 (如 "123    →")
        content = re.sub(r'^\s*\d+\s*→\s*', '', content, flags=re.MULTILINE)
        # 清理多餘空白
        content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
        return content.strip()
    
    def _extract_references(self, content: str) -> List[str]:
        """提取引用文獻"""
        references = re.findall(r'\[(\d+(?:,\s*\d+)*)\]', content)
        return [ref.strip() for ref_group in references for ref in ref_group.split(',')]
    
    def process_document(self) -> List[DocumentChunk]:
        """處理文檔並生成chunks"""
        current_part = ("0", "Unknown")
        current_section = ("0.0", "Unknown")
        current_content = []
        line_start = 0
        
        for i, line in enumerate(self.lines):
            line = line.strip()
            
            # 跳過空行和分隔符
            if not line or line.startswith('---'):
                if line.startswith('---') and current_content:
                    # 遇到分隔符，結束當前chunk
                    self._create_chunk(current_content, current_part, current_section, line_start, i)
                    current_content = []
                    line_start = i + 1
                continue
            
            # 檢查是否為新的Part
            part_info = self._extract_part_info(line)
            if part_info:
                # 保存之前的內容
                if current_content:
                    self._create_chunk(current_content, current_part, current_section, line_start, i-1)
                
                current_part = part_info
                current_section = ("0.0", "Part Overview")
                current_content = [line]
                line_start = i
                continue
            
            # 檢查是否為新的Section
            section_info = self._extract_section_info(line)
            if section_info:
                # 保存之前的內容
                if current_content and len(current_content) > 1:  # 至少有標題和內容
                    self._create_chunk(current_content, current_part, current_section, line_start, i-1)
                
                current_section = section_info
                current_content = [line]
                line_start = i
                continue
            
            # 添加到當前內容
            current_content.append(line)
        
        # 處理最後一個chunk
        if current_content:
            self._create_chunk(current_content, current_part, current_section, line_start, len(self.lines)-1)
        
        return self.chunks
    
    def _create_chunk(self, content_lines: List[str], part_info: Tuple[str, str], 
                     section_info: Tuple[str, str], start_line: int, end_line: int) -> None:
        """創建文檔塊"""
        if not content_lines:
            return
            
        content = '\n'.join(content_lines)
        clean_content = self._clean_content(content)
        
        if len(clean_content.strip()) < 50:  # 跳過太短的內容
            return
        
        # 確定內容類型
        content_type = "paragraph"
        if any(self._is_table_line(line) for line in content_lines):
            content_type = "table"
        elif any(line.strip().startswith('*') or line.strip().startswith('-') for line in content_lines):
            content_type = "list"
        
        # 提取引用
        references = self._extract_references(clean_content)
        
        # 生成chunk ID
        chunk_id = f"lastwar_part{part_info[0]}_sec{section_info[0].replace('.', '_')}_line{start_line}_{end_line}"
        
        # 創建metadata
        metadata = {
            "source_file": "Last War manual.md",
            "part_number": part_info[0],
            "part_title": part_info[1],
            "section_number": section_info[0],
            "section_title": section_info[1],
            "content_type": content_type,
            "line_range": f"{start_line}-{end_line}",
            "references": json.dumps(references) if references else "",
            "chunk_length": str(len(clean_content)),
            "game": "Last War: Survival",
            "document_type": "game_manual"
        }
        
        chunk = DocumentChunk(
            content=clean_content,
            metadata=metadata,
            chunk_id=chunk_id
        )
        
        self.chunks.append(chunk)
        print(f"創建chunk: Part {part_info[0]}.{section_info[0]} - {len(clean_content)} chars")
    
    def save_chunks_to_json(self, output_path: str) -> None:
        """保存chunks到JSON文件"""
        chunks_data = []
        for chunk in self.chunks:
            chunks_data.append({
                "id": chunk.chunk_id,
                "content": chunk.content,
                "metadata": chunk.metadata
            })
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(chunks_data, f, ensure_ascii=False, indent=2)
        
        print(f"已保存 {len(chunks_data)} 個chunks到 {output_path}")
    
    def get_statistics(self) -> Dict[str, any]:
        """獲取處理統計信息"""
        stats = {
            "total_chunks": len(self.chunks),
            "parts": {},
            "content_types": {},
            "total_content_length": 0
        }
        
        for chunk in self.chunks:
            # 按Part統計
            part_num = chunk.metadata["part_number"]
            if part_num not in stats["parts"]:
                stats["parts"][part_num] = {
                    "title": chunk.metadata["part_title"],
                    "chunk_count": 0,
                    "total_length": 0
                }
            stats["parts"][part_num]["chunk_count"] += 1
            stats["parts"][part_num]["total_length"] += len(chunk.content)
            
            # 按內容類型統計
            content_type = chunk.metadata["content_type"]
            stats["content_types"][content_type] = stats["content_types"].get(content_type, 0) + 1
            
            stats["total_content_length"] += len(chunk.content)
        
        return stats

def main():
    """主函數"""
    # 自動檢測工作目錄
    current_dir = Path(__file__).parent.parent
    manual_path = current_dir / "Last War manual.md"
    output_path = current_dir / "lastwar_manual_chunks.json"
    
    processor = LastWarManualProcessor(str(manual_path))
    
    print("開始處理Last War手冊...")
    processor.load_document()
    
    chunks = processor.process_document()
    print(f"處理完成，共生成 {len(chunks)} 個chunks")
    
    # 保存到JSON
    processor.save_chunks_to_json(str(output_path))
    
    # 顯示統計信息
    stats = processor.get_statistics()
    print("\n=== 處理統計 ===")
    print(f"總chunks數: {stats['total_chunks']}")
    print(f"總內容長度: {stats['total_content_length']} 字符")
    print(f"\n各部分統計:")
    for part_num, part_info in stats["parts"].items():
        print(f"  Part {part_num}: {part_info['title']}")
        print(f"    Chunks: {part_info['chunk_count']}, 長度: {part_info['total_length']}")
    print(f"\n內容類型統計:")
    for content_type, count in stats["content_types"].items():
        print(f"  {content_type}: {count}")

if __name__ == "__main__":
    main()
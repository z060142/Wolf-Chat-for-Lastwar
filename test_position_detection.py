#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
職位頁面檢測測試
測試確保可以:
1. 偵測到正在職位頁面 (president_title)
2. 偵測到5個職位按鈕都在頁面裡
"""

import os
import sys
import time
from typing import Dict, List, Tuple, Optional

# 添加當前目錄到Python路徑
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ui_interaction import DetectionModule, InteractionModule

class PositionPageDetector:
    """職位頁面檢測器"""
    
    def __init__(self):
        # 模板路徑定義
        TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
        
        # 職位頁面相關模板
        self.templates = {
            # 頁面識別模板
            'president_title': os.path.join(TEMPLATE_DIR, "capitol", "president_title.png"),
            
            # 五個職位按鈕模板
            'position_development': os.path.join(TEMPLATE_DIR, "capitol", "position_development.png"),
            'position_interior': os.path.join(TEMPLATE_DIR, "capitol", "position_interior.png"),
            'position_science': os.path.join(TEMPLATE_DIR, "capitol", "position_science.png"),
            'position_security': os.path.join(TEMPLATE_DIR, "capitol", "position_security.png"),
            'position_strategy': os.path.join(TEMPLATE_DIR, "capitol", "position_strategy.png"),
        }
        
        # 初始化UI檢測器
        self.detector = DetectionModule(self.templates)
        
        # 職位名稱映射
        self.position_names = {
            'position_development': '發展部長',
            'position_interior': '內政部長',
            'position_science': '科技部長',
            'position_security': '安全部長',
            'position_strategy': '戰略部長'
        }
    
    def check_templates_exist(self) -> bool:
        """檢查所有模板文件是否存在"""
        print("=== 檢查模板文件 ===")
        all_exist = True
        
        for template_key, template_path in self.templates.items():
            if os.path.exists(template_path):
                print(f"[OK] {template_key}: {template_path}")
            else:
                print(f"[FAIL] {template_key}: {template_path} (文件不存在)")
                all_exist = False
        
        print(f"\n模板文件檢查結果: {'通過' if all_exist else '失敗'}")
        return all_exist
    
    def detect_position_page(self, confidence: float = 0.8) -> bool:
        """
        檢測是否在職位頁面
        通過檢測 president_title 模板來確認
        """
        print(f"\n=== 檢測職位頁面 (confidence={confidence}) ===")
        
        try:
            # 檢測總統標題
            title_locations = self.detector._find_template('president_title', confidence=confidence)
            
            if title_locations:
                print(f"[PASS] 偵測到職位頁面! 總統標題位置: {title_locations[0]}")
                return True
            else:
                print("[FAIL] 未偵測到職位頁面 (沒有找到總統標題)")
                return False
                
        except Exception as e:
            print(f"✗ 職位頁面檢測失敗: {e}")
            return False
    
    def detect_all_positions(self, confidence: float = 0.8) -> Dict[str, List[Tuple[int, int]]]:
        """
        檢測所有五個職位按鈕
        返回每個職位的檢測結果
        """
        print(f"\n=== 檢測五個職位按鈕 (confidence={confidence}) ===")
        
        position_keys = ['position_development', 'position_interior', 'position_science', 
                        'position_security', 'position_strategy']
        
        results = {}
        
        try:
            # 批量檢測所有職位
            detection_results = self.detector.find_elements(position_keys, confidence=confidence)
            
            for position_key in position_keys:
                locations = detection_results.get(position_key, [])
                results[position_key] = locations
                
                position_name = self.position_names.get(position_key, position_key)
                
                if locations:
                    print(f"[PASS] {position_name}: 發現 {len(locations)} 個位置 {locations}")
                else:
                    print(f"[FAIL] {position_name}: 未檢測到")
            
            return results
            
        except Exception as e:
            print(f"✗ 職位檢測過程發生錯誤: {e}")
            return {}
    
    def run_comprehensive_test(self, confidence: float = 0.8) -> bool:
        """
        執行完整測試
        1. 檢測職位頁面
        2. 檢測五個職位按鈕
        """
        print("=" * 60)
        print("職位頁面檢測測試開始")
        print("=" * 60)
        
        # 檢查模板文件
        if not self.check_templates_exist():
            print("\n測試失敗: 模板文件缺失")
            return False
        
        # 測試1: 檢測職位頁面
        is_position_page = self.detect_position_page(confidence)
        
        # 測試2: 檢測五個職位
        position_results = self.detect_all_positions(confidence)
        
        # 統計結果
        detected_positions = [key for key, locations in position_results.items() if locations]
        missing_positions = [key for key, locations in position_results.items() if not locations]
        
        print(f"\n=== 測試結果總結 ===")
        print(f"職位頁面檢測: {'[PASS] 通過' if is_position_page else '[FAIL] 失敗'}")
        print(f"檢測到的職位: {len(detected_positions)}/5")
        
        for position_key in detected_positions:
            position_name = self.position_names.get(position_key, position_key)
            print(f"  [PASS] {position_name}")
        
        if missing_positions:
            print("未檢測到的職位:")
            for position_key in missing_positions:
                position_name = self.position_names.get(position_key, position_key)
                print(f"  [FAIL] {position_name}")
        
        # 判斷測試是否通過
        test_passed = is_position_page and len(detected_positions) == 5
        
        print(f"\n整體測試結果: {'[PASS] 全部通過' if test_passed else '[FAIL] 部分失敗'}")
        
        if not test_passed:
            print("\n建議:")
            if not is_position_page:
                print("- 請確認遊戲已打開並處於職位頁面")
                print("- 檢查president_title.png模板是否正確")
            if len(detected_positions) < 5:
                print(f"- 只檢測到 {len(detected_positions)} 個職位，請檢查職位按鈕模板")
                print("- 可能需要調整confidence參數或更新模板圖片")
        
        return test_passed


def main():
    """主函數"""
    print("職位頁面檢測測試工具")
    print("請確保遊戲已打開並處於職位頁面")
    print("開始自動測試...")
    
    # 創建檢測器並運行測試
    detector = PositionPageDetector()
    
    try:
        # 可以調整confidence參數
        confidence = 0.8
        print(f"\n使用confidence: {confidence}")
        
        # 執行測試
        result = detector.run_comprehensive_test(confidence)
        
        if result:
            print("\n[SUCCESS] 恭喜! 所有測試都通過了!")
        else:
            print("\n[WARNING] 測試未完全通過，請檢查上述建議")
            
    except KeyboardInterrupt:
        print("\n測試被用戶中斷")
    except Exception as e:
        print(f"\n測試過程發生錯誤: {e}")


if __name__ == "__main__":
    main()
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
檢查職位檢測位置是否重疊
"""

import math
from typing import List, Tuple, Dict

def calculate_distance(pos1: Tuple[int, int], pos2: Tuple[int, int]) -> float:
    """計算兩個位置之間的距離"""
    return math.sqrt((pos1[0] - pos2[0])**2 + (pos1[1] - pos2[1])**2)

def analyze_position_overlaps():
    """分析職位檢測結果的重疊情況"""
    
    # 從測試結果提取的位置數據
    positions = {
        '發展部長': [(220, 1160), (220, 1161), (221, 1161), (220, 1162)],
        '內政部長': [(654, 1160), (654, 1161), (654, 1162)],
        '科技部長': [(437, 1161), (437, 1162), (438, 1162), (437, 1163)],
        '安全部長': [(653, 885), (653, 886), (653, 885)],  # 修正重複的885
        '戰略部長': [(437, 880), (436, 881), (437, 881), (438, 881), (654, 881), (437, 882)]
    }
    
    print("=== 職位檢測位置分析 ===")
    
    # 分析每個職位內部的位置分布
    for position_name, coords_list in positions.items():
        print(f"\n{position_name}:")
        print(f"  檢測到 {len(coords_list)} 個位置")
        
        if len(coords_list) > 1:
            # 計算位置間的最小和最大距離
            distances = []
            for i in range(len(coords_list)):
                for j in range(i+1, len(coords_list)):
                    dist = calculate_distance(coords_list[i], coords_list[j])
                    distances.append(dist)
            
            min_dist = min(distances) if distances else 0
            max_dist = max(distances) if distances else 0
            
            print(f"  位置範圍: X({min(c[0] for c in coords_list)}-{max(c[0] for c in coords_list)}), Y({min(c[1] for c in coords_list)}-{max(c[1] for c in coords_list)})")
            print(f"  內部距離: 最小 {min_dist:.1f}px, 最大 {max_dist:.1f}px")
            
            # 如果距離很小，可能是同一個按鈕的多次檢測
            if max_dist <= 5:
                print(f"  [分析] 可能是同一按鈕的精確匹配 (距離<5px)")
            elif max_dist <= 20:
                print(f"  [分析] 可能是同一按鈕的模糊匹配 (距離<20px)")
            else:
                print(f"  [警告] 位置分散較大，可能檢測到多個不同元素")
        else:
            print(f"  位置: {coords_list[0]}")
    
    print("\n=== 跨職位重疊檢查 ===")
    
    # 獲取每個職位的代表性位置 (取第一個檢測到的位置)
    representative_positions = {}
    for position_name, coords_list in positions.items():
        if coords_list:
            representative_positions[position_name] = coords_list[0]
    
    # 檢查職位間的距離
    position_names = list(representative_positions.keys())
    overlaps_found = False
    
    for i in range(len(position_names)):
        for j in range(i+1, len(position_names)):
            name1, name2 = position_names[i], position_names[j]
            pos1, pos2 = representative_positions[name1], representative_positions[name2]
            
            distance = calculate_distance(pos1, pos2)
            
            print(f"{name1} vs {name2}:")
            print(f"  位置: {pos1} vs {pos2}")
            print(f"  距離: {distance:.1f}px")
            
            if distance < 50:  # 如果兩個職位的距離小於50px，認為可能重疊
                print(f"  [警告] 距離較近，可能存在重疊或誤檢")
                overlaps_found = True
            elif distance < 100:
                print(f"  [注意] 距離較近，但應該是不同的按鈕")
            else:
                print(f"  [正常] 距離合理，不同區域的按鈕")
            print()
    
    print("=== 總結 ===")
    if not overlaps_found:
        print("[OK] 沒有發現明顯的重疊問題，各職位檢測位置分布合理")
    else:
        print("[WARNING] 發現一些位置較近的情況，建議進一步檢查")
    
    print("\n=== Y座標分析 (檢查是否在同一排) ===")
    y_coords = []
    for position_name, coords_list in positions.items():
        for coord in coords_list:
            y_coords.append((position_name, coord[1]))
    
    # 按Y座標分組
    y_groups = {}
    for position_name, y in y_coords:
        y_group = round(y / 50) * 50  # 以50px為分組基準
        if y_group not in y_groups:
            y_groups[y_group] = []
        y_groups[y_group].append((position_name, y))
    
    for y_group, positions_in_group in y_groups.items():
        print(f"Y座標 ~{y_group}px 附近:")
        for position_name, actual_y in positions_in_group:
            print(f"  {position_name}: Y={actual_y}")

if __name__ == "__main__":
    analyze_position_overlaps()
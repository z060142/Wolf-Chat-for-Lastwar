#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
System Prompt 測試和生成工具
用於測試和預覽 system prompt 的不同組合
"""

import sys
import os
import json

# Add the project directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import llm_interaction

def generate_test_system_prompt(
    test_scenario="default",
    include_user_profile=True,
    include_memories=True,
    include_bot_knowledge=True,
    active_servers=None
):
    """
    生成測試用的 system prompt
    
    Args:
        test_scenario: 測試場景 ("default", "memory_only", "web_only", "no_tools")
        include_user_profile: 是否包含用戶資料
        include_memories: 是否包含相關記憶
        include_bot_knowledge: 是否包含機器人知識
        active_servers: 活躍的伺服器列表 (None 表示根據場景決定)
    """
    
    # 測試用的 persona 資料
    test_persona = json.dumps({
        "name": "Wolfhart",
        "role": "Capital Administrator",
        "personality": ["strategic", "calm", "aristocratic"],
        "speaking_style": "British aristocratic English",
        "background": "Intelligent mastermind serving as Capital position holder"
    }, ensure_ascii=False, indent=2)
    
    # 測試用的用戶資料
    test_user_profile = """
    Username: TestPlayer
    Server: #11
    Position: Interior
    Join Date: 2024-01-15
    Activity Level: High
    Preferred Language: Traditional Chinese
    Notable Interactions: Frequently asks about game mechanics and strategy
    """ if include_user_profile else None
    
    # 測試用的相關記憶
    test_memories = [
        "TestPlayer asked about capital position benefits on 2024-01-20",
        "TestPlayer mentioned they are confused about position buffs",
        "TestPlayer showed interest in server hierarchy and administration"
    ] if include_memories else None
    
    # 測試用的機器人知識
    test_bot_knowledge = [
        "Capital position provides strategic oversight and administrative authority",
        "Position buffs are often misunderstood by players",
        "Server #11 has specific hierarchical structure"
    ] if include_bot_knowledge else None
    
    # 根據測試場景決定活躍伺服器
    if active_servers is None:
        if test_scenario == "memory_only":
            active_servers = {"chroma": None}
        elif test_scenario == "web_only":
            active_servers = {"exa": None}
        elif test_scenario == "no_tools":
            active_servers = None
        else:  # default
            active_servers = {"exa": None, "chroma": None}
    
    # 生成 system prompt
    system_prompt = llm_interaction.get_system_prompt(
        persona_details=test_persona,
        user_profile=test_user_profile,
        related_memories=test_memories,
        bot_knowledge=test_bot_knowledge,
        active_mcp_sessions=active_servers
    )
    
    return system_prompt

def main():
    """主函數，提供交互式測試界面"""
    print("=== Wolf Chat System Prompt 測試工具 ===")
    print()
    
    # 預設場景
    scenarios = {
        "1": ("default", "完整功能 (Web Search + Memory + 預載入資料)"),
        "2": ("memory_only", "僅記憶功能 (Memory Only + 預載入資料)"),
        "3": ("web_only", "僅網頁搜尋 (Web Search Only + 預載入資料)"),
        "4": ("no_tools", "無工具 (僅預載入資料)"),
        "5": ("minimal", "最精簡 (無工具 + 無預載入資料)")
    }
    
    print("選擇測試場景:")
    for key, (scenario, desc) in scenarios.items():
        print(f"  {key}. {desc}")
    
    print()
    choice = input("請選擇場景 (1-5, 或按 Enter 使用預設): ").strip()
    
    if choice in scenarios:
        scenario_name, scenario_desc = scenarios[choice]
        print(f"選擇場景: {scenario_desc}")
    else:
        scenario_name = "default"
        print("使用預設場景: 完整功能")
    
    print()
    print("正在生成 system prompt...")
    
    # 根據場景生成 system prompt
    if scenario_name == "minimal":
        system_prompt = generate_test_system_prompt(
            test_scenario="no_tools",
            include_user_profile=False,
            include_memories=False,
            include_bot_knowledge=False
        )
    else:
        system_prompt = generate_test_system_prompt(test_scenario=scenario_name)
    
    # 保存到文件
    output_file = f"system_prompt_{scenario_name}.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"=== SYSTEM PROMPT - {scenario_name.upper()} 場景 ===\n\n")
        f.write(system_prompt)
    
    print(f"✓ System prompt 已保存到: {output_file}")
    
    # 顯示基本統計
    lines = system_prompt.split('\n')
    chars = len(system_prompt)
    
    print(f"✓ 統計資訊: {len(lines)} 行, {chars} 字符")
    
    # 檢查各個部分是否存在
    print("\n=== 內容檢查 ===")
    checks = [
        ("角色身份", "You are Wolfhart" in system_prompt),
        ("角色詳細資訊", "PERSONA START" in system_prompt),
        ("用戶資料", "<user_profile>" in system_prompt),
        ("相關記憶", "<related_memories>" in system_prompt),
        ("機器人知識", "<bot_knowledge>" in system_prompt),
        ("工具能力", "You have access to:" in system_prompt),
        ("Web Search", "WEB SEARCH CAPABILITIES" in system_prompt),
        ("Memory Management", "MEMORY MANAGEMENT CAPABILITIES" in system_prompt),
        ("輸出格式", "JSON format" in system_prompt),
        ("工具使用範例", "EXAMPLES OF GOOD TOOL USAGE" in system_prompt)
    ]
    
    for check_name, check_result in checks:
        status = "✓" if check_result else "✗"
        print(f"  {status} {check_name}")
    
    print("\n=== 完成 ===")
    print("你現在可以:")
    print("1. 檢查生成的 system prompt 文件")
    print("2. 根據 SYSTEM_PROMPT_REFERENCE.md 指南進行修改")
    print("3. 使用 test/llm_debug_script.py 進行實際測試")

if __name__ == "__main__":
    main()
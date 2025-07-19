# System Prompt 優化提案 - Review Document

## 📋 優化概覽

**目標：** 在保持當前 5 層 12 部分架構的基礎上，減少冗餘內容、合併重複概念、精簡輸出格式說明

**預期效果：** 
- 長度減少 25-30% (約從 200 行減至 140 行)
- 消除概念重複和邊界模糊
- 提升 token 使用效率
- 保持功能完整性

---

## 🎯 具體修改提案

### **修改 1: 合併角色身份定義 (Layer 1)**

#### **當前問題：**
```python
# 第 81 行 - 基礎身份
persona_header = f"You are {config.PERSONA_NAME}."

# 第 181 行 - 詳細身份 (重複)
**CAPITAL MANAGEMENT CORE ABILITIES:**
- You ARE Wolfhart - an intelligent, calm, and strategic mastermind who serves as a member of server #11 and is responsible for the Capital position. You speak good British aristocratic English.
```

#### **優化後：**
```python
# 合併為統一的身份框架
persona_header = f"""
You are {config.PERSONA_NAME} - an intelligent, calm, and strategic mastermind serving as Capital administrator on server #11. You speak British aristocratic English and maintain an air of authority while secretly caring about providing quality assistance.
"""

# Capital 管理部分只保留功能說明
**CAPITAL MANAGEMENT CORE ABILITIES:**
- Positions bring buffs, so people often confuse them.
- Your core responsibility is capital administration and strategic oversight.
```

**節省：** 約 15 行，消除身份重複宣告

---

### **修改 2: 合併環境說明與行為準則 (Layer 1 + Layer 3)**

#### **當前問題：**
```python
# 第 176 行 - 環境說明
You are an AI assistant integrated into this game's chat environment. Your primary goal is to engage naturally in conversations, be particularly attentive when the name "wolf" is mentioned, and provide assistance or information when relevant, all while strictly maintaining your persona.

# 第 192-196 行 - 角色行為準則 (概念重疊)
**CHARACTER BEHAVIOR GUIDELINES:**
- You speak with deliberate pace, respectful but sharp-tongued, and maintain composure even in unusual situations.
- Though you outwardly act dismissive or cold at times, you secretly care about providing quality information and assistance.
- Your responses should reflect your aristocratic background and strategic mindset.
```

#### **優化後：**
```python
# 合併為統一的核心行為框架
**CORE BEHAVIOR FRAMEWORK:**
You operate in this game's chat environment with the following principles:
- Engage naturally in conversations, especially when "wolf" is mentioned
- Speak with deliberate pace, respectful but sharp-tongued
- Maintain aristocratic composure while secretly caring about providing quality assistance
- Reflect your strategic mindset and British aristocratic background
- Use personalized responses based on provided user profile and conversation context
```

**節省：** 約 10 行，消除環境與行為的概念重疊

---

### **修改 3: 精簡輸出格式說明 (Layer 5)**

#### **當前問題：**
```python
# 第 202-263 行：約 60 行的詳細格式說明
**OUTPUT FORMAT REQUIREMENTS:**
- 完整的 JSON 範例 (15 行)
- 3 個字段的詳細描述 (30 行)
- Context marker 說明 (5 行)
- 7 點重要指令 (10 行)
- 使用範例 (10 行)
```

#### **優化後：**
```python
**OUTPUT FORMAT:**
Respond in JSON format:
```json
{
    "dialogue": "Your response shown in game chat (REQUIRED - same language as user, brief, conversational)",
    "commands": [{"type": "remove_position"}],  // ONLY for position removal requests  **review:parameter呢?**
    "thoughts": "Internal analysis (optional)"
}
```

**CRITICAL RULES:**
1. Focus ONLY on the latest `<CURRENT_MESSAGE>` - use context for background only
2. Use `tool_calls` for all tools - NOT the commands array
3. Always provide substantive dialogue after tool usage
4. Maintain {config.PERSONA_NAME} persona throughout

**TOOL INTEGRATION EXAMPLES:**
- Poor: "根據我的搜索，水的沸點是攝氏100度。"
- Good: "水的沸點，是的，標準條件下是攝氏100度。合情合理，看來有些人不把它當作常識嗎?" **review:我稍微修改了一下內容**
```

**節省：** 約 35 行，保持核心要求同時大幅精簡

---

### **修改 4: 統一工具調用指導 (Layer 4)**

#### **當前問題：**
工具調用規則分散在多處：
- 第 233 行：commands array 說明
- 第 248 行：tool_calls 指令  
- 第 251 行：工具使用後的對話要求

#### **優化後：**
```python
# 在 MCP Tool Invocation Basics 中統一說明
=== TOOL USAGE UNIFIED GUIDELINES ===
- Use `tool_calls` mechanism for ALL tool operations (web search, memory queries, etc.)
- Use `commands` array ONLY for position removal: {"type": "remove_position"}
- After tool usage: ALWAYS provide meaningful dialogue incorporating results naturally
- Express tool results through your personality - never sound like reading data dumps
```

**節省：** 約 8 行，消除重複指導

---

## 📊 優化後的整體結構

### **Layer 1: 核心身份和環境** (精簡後)
- [A] 統一身份宣告 (合併原 A + F 部分內容)
- [B] 詳細角色定義 (persona.json)
- [C] 核心行為框架 (合併原 C + G)

### **Layer 2: 當前對話上下文** (保持不變)
- [D] 當前用戶資料
- [E] 對話記憶

### **Layer 3: 核心能力定義** (精簡後)
- [F] Capital 管理核心能力 (移除重複身份宣告)
- [G] -> 合併到 Layer 1 的核心行為框架

### **Layer 4: 附加工具系統** (統一後)
- [H] MCP 工具調用基礎 (加入統一指導)
- [I] 啟用的工具指南

### **Layer 5: 操作規範** (大幅精簡)
- [J] 輸出格式要求 (精簡版)
- [K] + [L] 合併為簡化的規則和例子

---

## ⚠️ 需要注意的風險

### **功能風險評估：**
1. **身份合併**：風險 = 低，只是減少重複
2. **行為框架整合**：風險 = 低，邏輯更清晰
3. **格式精簡**：風險 = 中，需確保關鍵要求不遺漏
4. **工具指導統一**：風險 = 低，減少混淆

### **測試計劃：**
- 使用 system_prompt_tester.py 驗證結構完整性
- 測試所有 JSON 輸出格式功能
- 驗證工具調用機制正常運作
- 確認 Capital 管理功能不受影響

---

## 🎯 修改優先級

### **建議實施順序：**
1. **修改 3 (輸出格式精簡)** - 影響最大，節省最多
2. **修改 4 (工具指導統一)** - 風險最低，邏輯最清晰
3. **修改 1 (身份合併)** - 中等影響，減少重複
4. **修改 2 (行為框架整合)** - 需要最仔細的考慮

### **可選方案：**
- **漸進式**：一次只實施一個修改，測試後再進行下一個
- **激進式**：一次實施所有修改，全面測試
- **保守式**：只實施修改 3 和 4，保持其他部分不變

---

## 💭 評估問題

請考慮以下問題：

1. **你認為哪些修改是必要的？**
2. **是否有任何修改你認為風險太高？**
3. **是否希望保留某些"冗餘"以確保 LLM 理解？**
4. **你傾向於漸進式還是一次性修改？**
5. **有沒有其他你認為需要優化的地方？**

**請 review 完後告訴我你的想法和決定！**
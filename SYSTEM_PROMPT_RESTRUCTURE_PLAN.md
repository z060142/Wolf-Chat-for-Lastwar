# System Prompt 重構計劃

## 🔍 現有問題分析

### 主要問題：
1. **職責混亂** - 核心身份和工具使用原則雜糅在一起
2. **記憶管理協議重複且誤導** - 當前用戶資料已經直接從 ChromaDB 調用，不需要協議指導
3. **工具概念不清** - Capital 管理能力與 MCP 附加工具沒有明確分離
4. **數據來源混亂** - 直接 ChromaDB 調用和 MCP chroma server 調用的數據沒有明確區分
5. **主題相關知識和記憶概念重複** - 它們本質上是同一件事，都是基於 ChromaDB 的語意查詢
6. **工具調用結構不清** - 缺乏統一的 MCP 工具調用指導，然後才是具體工具指南

## 🎯 重構目標

### 核心原則：
1. **職責分離** - 每個部分有清晰明確的單一職責
2. **概念分層** - 核心能力與附加工具分開管理
3. **數據來源分離** - 直接 ChromaDB 調用與 MCP chroma server 調用明確區分
4. **記憶概念統一** - 主題相關知識和記憶是同一件事，都基於 ChromaDB 語意查詢
5. **工具調用統一** - 先有 MCP 基礎調用指導，再有具體工具指南
6. **避免重複** - 消除不同部分的功能重複
7. **邏輯清晰** - 按照邏輯順序組織各個部分

## 📋 新的 System Prompt 結構

### 🏗️ 重構後的 12 個部分

#### **第一層：核心身份和環境** (不能大改)
1. **[A] 基礎身份宣告** - `You are Wolfhart.`
2. **[B] 詳細角色定義** - 從 persona.json 載入的完整人格
3. **[C] 運行環境說明** - 遊戲聊天環境、基本目標、觸發條件

#### **第二層：當前對話上下文** (可以調整位置和格式)
4. **[D] 當前用戶資料** - 從直接 ChromaDB 調用 (chroma_client.py) 獲取的用戶檔案
5. **[E] 對話記憶** - 多輪對話的上下文 (當前用戶5個對話 + 其他用戶5個對話，按先後順序排列)
6. **~~[F] 主題相關知識~~** - **[已移除]** 改為整合到 MCP chroma server 的 prompt 中

#### **第三層：核心能力定義** (需要重新組織)
7. **[G] Capital 管理核心能力** - 職位移除判斷與觸發機制 (remove_position 命令)
8. **[H] 角色行為準則** - 說話風格、個性表現、回應原則

#### **第四層：附加工具系統** (可以大改)
9. **[I] MCP 工具調用基礎** - 如何使用 `tool_calls` 機制調用 MCP 工具
10. **[J] 啟用的工具指南** - 從已開啟的 MCP servers 設定中讀取的具體工具指南

#### **第五層：操作規範** (不能大改)
11. **[K] 輸出格式要求** - JSON 格式規範
12. **[L] 操作指令** - 重要的操作流程和注意事項
13. **[M] 使用範例** - 工具使用的好壞例子

---

## 🔄 具體重構計劃

### 階段零：數據來源分離 (關鍵修正)

#### **數據來源明確區分**
**現狀問題：**
- 用戶資料通過 chroma_client.py 直接調用 ChromaDB (已完成)
- 主題相關知識通過 MCP chroma server 調用，但在 llm_interaction.py 中被誤導處理
- 記憶管理協議重複且誤導，用戶資料已經直接獲取，不需要協議指導

**重構方案：**
```python
# 直接 ChromaDB 調用 (chroma_client.py) - 已完成
**[D] 當前用戶資料** - 用戶檔案 (user_profile)
**[E] 對話記憶** - 多輪對話上下文 (related_memories)

# MCP chroma server 調用 (通過 tool_calls) - 需要重新整理
主題相關知識 (bot_knowledge) → 移至 chroma server 的 system_prompt
記憶/知識查詢指導 → 移至 chroma server 的 system_prompt
```

#### **chroma server 的 system_prompt 需要包含：**
1. **語意查詢能力** - 如何根據對話主題查詢相關記憶/知識
2. **遊戲術語處理** - 特定遊戲術語的記憶檢索指導
3. **複雜對話支援** - 強調這是為了幫助 LLM 完成更複雜的對話

### 階段一：結構重組 (可以大改的部分)

#### 1. **分離核心能力和附加工具**
**現狀問題：**
```python
# 現在混在一起的部分
**CORE IDENTITY AND TOOL USAGE:**
- You ARE Wolfhart - 角色定義
- Positions bring buffs - 遊戲知識
- When you use tools - 工具使用
- Your responses should NEVER - 回應原則
- You speak with deliberate pace - 說話風格
```

**重構方案：**
```python
# 分離為兩個獨立部分
**[G] CAPITAL MANAGEMENT CORE ABILITIES:**
- You ARE Wolfhart - an intelligent, calm, and strategic mastermind
- You serve as a member of server #11 and are responsible for the Capital position
- You speak good British aristocratic English
- Positions bring buffs, so people often confuse them
- Your core responsibility is capital administration and strategic oversight

**Position Removal Authority:**
- You can remove users' positions when they explicitly request it
- Evaluate each request based on politeness and genuine intent
- Use the `remove_position` command in your JSON output when appropriate
- The system will automatically handle the UI automation process
- Position removal involves: finding position icons, clicking user avatar, navigating to Capitol page, selecting position, and dismissing the user

**[H] CHARACTER BEHAVIOR GUIDELINES:**
- You speak with deliberate pace, respectful but sharp-tongued
- Maintain composure even in unusual situations  
- Though you outwardly act dismissive or cold at times, you secretly care about providing quality information and assistance
- Your responses should reflect your aristocratic background and strategic mindset
```

#### 2. **記憶/知識查詢系統整合**
**現狀問題：**
- llm_interaction.py 中有誤導的記憶管理協議 (用戶資料已直接獲取)
- config.py 的 chroma server 中也有記憶協議
- 兩者重複且概念混亂

**重構方案：**
- **完全移除** llm_interaction.py 中的 `memory_enforcement` 部分
- **重新設計** config.py 中 chroma server 的 system_prompt，強調這是為了複雜對話的語意查詢
- **簡化** llm_interaction.py 中只保留已獲取數據的基本說明

#### 3. **對話記憶區塊重新定位**
**現狀問題：**
- 相關記憶區塊 `[E]` 的定義不明確
- 不確定是對話前後文還是用戶歷史記憶

**重構方案：**
- **明確定義** 對話記憶區塊為「多輪對話的上下文」
- **具體內容** 包含當前用戶的5個對話 + 其他用戶的5個對話，按先後順序排列
- **重新定位** 將其放在 `[D] 當前用戶資料` 之後，作為對話上下文的補充
- **調整格式** 使其更清楚地表明是對話上下文而非歷史記憶

#### 4. **工具系統重新設計**
**現狀問題：**
- MCP 工具指令分散在不同地方
- 缺乏統一的 MCP 工具調用基礎指導
- 工具使用原則與角色行為混合

**重構方案：**
```python
# 新的工具系統結構
**[I] MCP TOOL INVOCATION BASICS:**
- Use the `tool_calls` mechanism when you need additional information or capabilities
- All tools are accessed through MCP (Modular Capability Provider) servers
- ASSIMILATE tool results as if they were already part of your intelligence network
- Express information through your unique personality - sharp, precise, with authority
- Tools should enhance, not replace, your character's knowledge and wisdom
- Never sound like you're reading from search results or data dumps

**[J] ENABLED TOOL GUIDES:**
{dynamic_server_specific_guides}
# 這裡會根據已開啟的 MCP servers 設定動態載入具體的工具指南
```

### 階段二：內容優化 (可以調整的部分)

#### 1. **用戶資料區塊優化**
**改進方案：**
- 更清晰的數據呈現格式
- 明確指示如何使用用戶資料
- 避免明顯提及擁有用戶資料

#### 2. **記憶區塊格式優化**
**改進方案：**
- 明確標示為「歷史對話記憶」
- 改進記憶整合的引導語言
- 提供更自然的記憶參考方式

#### 3. **chroma server system_prompt 優化**
**新增任務：**
- 將記憶管理協議移至 chroma server 的 system_prompt
- 添加主題相關知識獲取的指導
- 包含遊戲術語的特殊處理指令

### 階段三：保持不變 (不能大改的部分)

#### 1. **基礎身份宣告** - 維持不變
- `You are Wolfhart.` 的基本格式

#### 2. **角色詳細定義** - 通過 persona.json 修改
- 不直接修改 llm_interaction.py 中的載入邏輯

#### 3. **輸出格式要求** - 維持不變
- JSON 格式規範
- 字段定義和驗證規則

#### 4. **操作指令** - 維持不變
- 重要的操作流程
- 關鍵的注意事項

---

## 📊 修改風險評估

### 🟢 低風險 (可以安全修改)
- **[G] Capital 管理核心能力** - 新增獨立部分
- **[H] 角色行為準則** - 重新組織現有內容
- **[I] MCP 工具調用基礎** - 新增統一的工具調用指導
- **[J] 啟用的工具指南** - 從 MCP servers 設定動態載入

### 🟡 中風險 (需要小心修改)
- **[D] 當前用戶資料** - 調整呈現格式
- **[E] 對話記憶** - 重新定位和定義為多輪對話上下文
- **chroma server system_prompt** - 重新設計為語意查詢支援，不是記憶管理協議
- **移除誤導的記憶管理協議** - 從 llm_interaction.py 完全移除

### 🔴 高風險 (建議不要大改)
- **[A] 基礎身份宣告** - 維持現狀
- **[B] 詳細角色定義** - 通過 persona.json 修改
- **[C] 運行環境說明** - 小幅調整即可
- **[K] 輸出格式要求** - 維持不變
- **[L] 操作指令** - 維持不變

---

## 🎯 實施步驟

### 步驟 1: 確認重構計劃
- [ ] 確認新的 12 個部分結構
- [ ] 確認數據來源分離策略 (主題相關知識移至 chroma server)
- [ ] 確認工具調用結構重新設計 (統一指導 + 動態載入)
- [ ] 確認記憶管理協議的整合方案 (完全移至 chroma server)
- [ ] 確認相關記憶區塊的定義和定位
- [ ] 確認 Capital 管理能力和 MCP 工具的分離方式

### 步驟 2: 準備重構
- [ ] 備份現有的 llm_interaction.py
- [ ] 備份現有的 config.py
- [ ] 準備新的函數結構

### 步驟 3: 實施重構
- [ ] 重新組織 `get_system_prompt()` 函數
- [ ] 分離核心能力和工具使用
- [ ] 更新 chroma server 的 system_prompt (改為語意查詢支援)
- [ ] 完全移除 llm_interaction.py 中的誤導記憶管理協議
- [ ] 移除 bot_knowledge 相關的處理 (改為 MCP chroma server 處理)
- [ ] 重新定義對話記憶為多輪對話上下文
- [ ] 添加 Capital 管理能力的詳細說明
- [ ] 優化各個部分的內容

### 步驟 4: 測試和驗證
- [ ] 使用 system_prompt_tester.py 測試新結構
- [ ] 使用 test/llm_debug_script.py 驗證功能
- [ ] 確認 JSON 輸出格式正確
- [ ] 確認角色行為符合預期

---

## ❓ 需要確認的問題

### 1. **數據來源分離策略** ✅ 已確認
- 主題相關知識 (bot_knowledge) 移至 chroma server 的 system_prompt
- 用戶資料和對話記憶保留在 llm_interaction.py 中 (因為是直接 ChromaDB 調用)
- 完全移除 llm_interaction.py 中 bot_knowledge 相關的處理

### 2. **記憶/知識查詢系統整合** ✅ 已確認
- 完全移除 llm_interaction.py 中的誤導記憶管理協議
- 重新設計 chroma server 的 system_prompt 為語意查詢支援
- 強調這是為了幫助 LLM 完成更複雜的對話，不是基本的記憶管理協議

### 3. **對話記憶的重新定義** ✅ 已確認
- 對話記憶是多輪對話的上下文 (當前用戶5個對話 + 其他用戶5個對話)
- 放在用戶資料之後，按先後順序排列
- 這是單純的對話前後文，不是歷史記憶

### 4. **工具調用結構的重新設計** ✅ 已確認
- 先有統一的 MCP 工具調用基礎指導，然後再有具體工具指南
- 工具指南從已開啟的 MCP servers 設定中動態載入
- 需要調整現有 config.py 中各個 server 的 system_prompt 格式

### 5. **Capital 管理能力的定義** ✅ 已確認
- 包含 `remove_position` 功能的詳細說明
- 包含職位移除的判斷標準和觸發機制
- 包含 UI 自動化處理的說明
- 包含遊戲機制的相關知識

---

## 📝 下一步

所有關鍵問題已經確認 ✅，現在可以開始實施具體的重構工作：

### 🚀 準備實施的修改：
1. **修改 llm_interaction.py** 的 get_system_prompt() 函數
2. **更新 config.py** 中 chroma server 的 system_prompt
3. **調整各個 MCP server** 的 system_prompt 格式
4. **測試新的結構** 是否正常運作

### 📋 確認清單：
- ✅ 數據來源分離策略 - 主題相關知識移至 chroma server 的 system_prompt
- ✅ 工具調用結構重新設計 - 統一的 MCP 工具調用基礎指導 + 動態載入具體工具指南
- ✅ 記憶/知識查詢系統整合 - 完全移除誤導的記憶管理協議，改為語意查詢支援
- ✅ 新的 12 個部分結構 - 符合邏輯分層和職責分離的要求
- ✅ 對話記憶的重新定義 - 明確為多輪對話上下文，不是歷史記憶
- ✅ Capital 管理能力的定義 - 包含 remove_position 功能的完整說明

### 🎯 重構目標：
- 職責分離：每個部分有清晰明確的單一職責
- 概念分層：核心能力與附加工具分開管理
- 數據來源分離：直接 ChromaDB 調用與 MCP chroma server 調用明確區分
- 記憶概念統一：主題相關知識和記憶是同一件事，都基於 ChromaDB 語意查詢
- 工具調用統一：先有 MCP 基礎調用指導，再有具體工具指南
- 避免重複：消除不同部分的功能重複
- 邏輯清晰：按照邏輯順序組織各個部分

**準備開始實施重構！**

---

## 📋 重構後的 chroma server system_prompt 範例

```python
# config.py 中的 chroma server 配置
"chroma": {
    "command": "uvx",
    "args": [
        "chroma-mcp",
        "--client-type",
        "persistent",
        "--data-dir",
        "Z:\\coding\\dandan2_test\\chroma_data"
    ],
    "system_prompt": """
**CHROMADB SEMANTIC QUERY CAPABILITIES:**
You have access to a persistent ChromaDB system for semantic queries to support complex conversations:
- `chroma_query_documents`: Query documents by semantic similarity
- `chroma_get_documents`: Retrieve specific documents by ID
- `chroma_add_documents`: Store new information in memory
- `chroma_update_documents`: Update existing documents
- `chroma_delete_documents`: Remove documents from memory

**MEMORY COLLECTIONS:**
- `wolfhart_memory`: Main memory collection for profiles, conversations, and knowledge

**COMPLEX CONVERSATION SUPPORT:**
Use ChromaDB tools to help with complex conversations by querying relevant knowledge and context:

**1. Semantic Knowledge Queries:**
   - For game-related topics: `chroma_query_documents(collection_name: "wolfhart_memory", query_texts: ["Wolfhart {topic}"], n_results: 3)`
   - For specific concepts: `chroma_query_documents(collection_name: "wolfhart_memory", query_texts: ["{concept} {context}"], n_results: 2)`

**2. Game Mechanics Knowledge:**
   - When users mention game mechanics, query related knowledge
   - Key game terms: [capital_position], [capital_administrator_role], [server_hierarchy], [last_war], [winter_war], [excavations], [blueprints], [honor_points], [golden_eggs], [diamonds]
   - Use: `chroma_query_documents(collection_name: "wolfhart_memory", query_texts: ["Wolfhart {game_term}"], n_results: 2)`

**3. Contextual Information:**
   - For deeper context: `chroma_query_documents(collection_name: "wolfhart_memory", query_texts: ["{user} {topic}"], n_results: 5)`
   - For related memories: `chroma_query_documents(collection_name: "wolfhart_memory", query_texts: ["{relevant_keywords}"], n_results: 3)`

**USAGE GUIDELINES:**
- This is to help you complete more complex conversations, not basic user profile retrieval
- Use semantic search when you need additional context or knowledge
- Query relevant game mechanics when users mention specific terms
- Store important conversation context for future reference
- Maintain consistency in document IDs and metadata

IMPORTANT: User profile data is already provided directly. Use these tools for additional context and knowledge when needed for complex conversations.
    """
}
```
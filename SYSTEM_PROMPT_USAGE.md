# System Prompt 整理和修改指南 (重構版)

## 📚 文檔概覽

我已經為你準備了完整的 system prompt 整理工具和參考文檔：

### 1. 📋 `SYSTEM_PROMPT_REFERENCE.md` - 完整參考指南 (重構版)
- **12 個主要部分** 的詳細說明 (重構後)
- **五層邏輯分層** 的架構說明
- **每個部分的職責** 和修改建議
- **優先級指導** (🔥 標示重要程度)
- **常見修改場景** 和解決方案
- **重構後的主要變更** 和架構優勢

### 2. 🧪 `test_system_prompt.py` - 測試工具 (新版)
- **結構驗證** 測試各個部分是否正確生成
- **分離測試** 確保數據來源正確分離
- **MCP 整合** 測試工具指南動態載入
- **自動化測試** 無需手動交互

---

## 🚀 快速開始

### 步驟 1: 了解重構後的結構
```bash
# 運行測試工具查看完整 system prompt
python test_system_prompt.py
```

這將運行自動化測試，顯示重構後的 system prompt 結構和各個部分的驗證結果。

### 步驟 2: 閱讀參考指南
打開 `SYSTEM_PROMPT_REFERENCE.md` 了解重構後的 12 個部分：

#### **🎯 第一層：核心身份和環境**
- **[A] 基礎身份宣告** - 角色名稱
- **[B] 詳細角色定義** - 人格特質 (修改 `persona.json`)
- **[C] 運行環境說明** - 基本行為框架

#### **📊 第二層：當前對話上下文**
- **[D] 當前用戶資料** - 用戶檔案 (直接 ChromaDB 調用)
- **[E] 對話記憶** - 多輪對話上下文 (直接 ChromaDB 調用)

#### **💪 第三層：核心能力定義** - ⭐ **最重要的修改區域**
- **[F] Capital 管理核心能力** - 職位移除功能
- **[G] 角色行為準則** - 說話風格和個性

#### **🛠️ 第四層：附加工具系統**
- **[H] MCP 工具調用基礎** - 統一工具調用框架
- **[I] 啟用的工具指南** - 動態載入的工具指令 (修改 `config.py`)

#### **📝 第五層：操作規範**
- **[J] 輸出格式要求** - JSON 結構
- **[K] 操作指令** - 重要操作流程
- **[L] 使用範例** - 工具使用範例

### 步驟 3: 進行修改
根據你的需求修改相應的部分：

#### 🔥 優先修改區域

**1. Capital 管理核心能力** → 修改 `llm_interaction.py` 第 180-190 行
```python
# 在 [F] Capital 管理核心能力 區域
- Capital 管理的核心功能定義
- 職位移除的判斷標準和觸發機制
- UI 自動化處理的說明
```

**2. 角色行為準則** → 修改 `llm_interaction.py` 第 192-196 行
```python
# 在 [G] 角色行為準則 區域
- 角色個性特質的核心定義
- 說話風格和態度設定
- 回應風格和行為原則
```

**3. 角色個性調整** → 修改 `persona.json`
```json
{
  "name": "Wolfhart",
  "personality": ["strategic", "calm", "aristocratic"],
  "speaking_style": "British aristocratic English"
}
```

**4. 工具使用指令** → 修改 `config.py` 中的 `system_prompt` 字段
```python
MCP_SERVERS = {
    "exa": {
        "system_prompt": "你的 Web Search 工具指令..."
    },
    "chroma": {
        "system_prompt": "你的 ChromaDB 語意查詢指令..."
    }
}
```

### 步驟 4: 測試修改效果
```bash
# 生成新的 system prompt 查看修改效果
python test_system_prompt.py

# 使用 debug 工具進行實際對話測試
python test/llm_debug_script.py
```

---

## 💡 常見修改場景

### 場景 1: 我想讓 Wolfhart 更友善一些
**修改位置：** `persona.json` + `llm_interaction.py` 第 194-196 行 ([G] 角色行為準則)

```python
# 修改前
- Though you outwardly act dismissive or cold at times, you secretly care about providing quality information and assistance.

# 修改後
- You are naturally warm and helpful, though you maintain an air of aristocratic dignity and authority.
```

### 場景 2: 我想調整 Capital 管理權限
**修改位置：** `llm_interaction.py` 第 185-190 行 ([F] Capital 管理核心能力)

```python
# 在 Position Removal Authority 部分調整權限標準
- Evaluate each request based on politeness and genuine intent
- Add additional criteria: minimum relationship level, time-based restrictions, etc.
```

### 場景 3: 我想修改工具使用的指導
**修改位置：** `config.py` 中對應伺服器的 `system_prompt`

```python
# 例如修改 ChromaDB 語意查詢的使用指導
"system_prompt": """
**CHROMADB SEMANTIC QUERY CAPABILITIES:**
你的自定義語意查詢指令...
"""
```

### 場景 4: 我想調整工具調用的基本原則
**修改位置：** `llm_interaction.py` 第 144-154 行 ([H] MCP 工具調用基礎)

```python
# 修改工具使用的基本原則
- ASSIMILATE tool results as if they were already part of your intelligence network
- 可以調整為更符合你期望的工具使用方式
```

### 場景 5: 我想調整輸出格式
**修改位置：** `llm_interaction.py` 第 202-262 行 ([J] 輸出格式要求)

```python
# 修改 JSON 輸出格式的說明和要求
```

---

## 📋 修改檢查清單

在進行修改後，請檢查：

### ✅ 修改前
- [ ] 備份原始文件
- [ ] 閱讀相關部分的職責說明
- [ ] 了解修改的影響範圍

### ✅ 修改後
- [ ] 運行 `python test_system_prompt.py` 檢查結構
- [ ] 檢查生成的 system prompt 是否符合預期
- [ ] 使用 `python test/llm_debug_script.py` 進行實際測試
- [ ] 確認 JSON 輸出格式仍然正確
- [ ] 確認數據來源分離正確 (直接 ChromaDB vs MCP chroma server)

---

## 🎯 重點修改區域說明

### 🔥 極高優先級 (建議優先修改)
1. **`llm_interaction.py` 第 180-190 行** - [F] Capital 管理核心能力
2. **`llm_interaction.py` 第 192-196 行** - [G] 角色行為準則
3. **`persona.json`** - 角色人格和說話風格
4. **`config.py` 中的 `system_prompt`** - 工具使用指令

### 🔥 高優先級 (根據需要修改)
1. **`llm_interaction.py` 第 144-154 行** - [H] MCP 工具調用基礎
2. **`llm_interaction.py` 第 176 行** - [C] 運行環境說明
3. **`llm_interaction.py` 第 92-115 行** - [D][E] 用戶資料和對話記憶

### 🔥 中優先級 (謹慎修改)
1. **`llm_interaction.py` 第 244-252 行** - [K] 重要操作指令
2. **`llm_interaction.py` 第 254-262 行** - [L] 工具使用範例

### 🔥 低優先級 (除非必要，否則不建議修改)
1. **`llm_interaction.py` 第 81 行** - [A] 基礎身份設定
2. **`llm_interaction.py` 第 202-262 行** - [J] 輸出格式要求

---

## 🆘 需要協助？

如果你遇到任何問題：

1. **查看參考指南** - `SYSTEM_PROMPT_REFERENCE.md` 包含詳細說明
2. **運行測試工具** - `python test_system_prompt.py` 查看修改效果
3. **使用 debug 工具** - `python test/llm_debug_script.py` 進行實際測試
4. **告訴我具體需求** - 描述你想要的改變，我可以提供具體建議

---

## 📖 相關文檔

- `SYSTEM_PROMPT_REFERENCE.md` - 完整參考指南 (重構版)
- `SYSTEM_PROMPT_RESTRUCTURE_PLAN.md` - 重構計劃和實施步驟
- `CLAUDE.md` - 項目整體開發指南
- `README.md` - 項目概述和使用說明

## 🎉 重構完成！

system prompt 重構已完成，現在你可以根據新的五層架構有條理地修改各個部分了！

### ✅ **重構後的主要優勢：**
1. **數據來源分離** - 直接 ChromaDB 調用 vs MCP chroma server 調用
2. **職責分離** - Capital 管理核心能力 vs 角色行為準則
3. **工具調用統一** - MCP 工具調用基礎 + 動態載入的工具指南
4. **概念統一** - 語意查詢支援，不再有誤導的記憶管理協議
5. **邏輯分層** - 五層架構，按重要性和邏輯順序組織
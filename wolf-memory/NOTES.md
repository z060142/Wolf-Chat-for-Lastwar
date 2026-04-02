# Wolf Memory - 開發筆記

## 專案目標

一個先進的、AI 驅動的記憶管理工具，給 chatbot（Wolf Chat）使用。
支援查詢、新增、更新/整理記憶，以工程化分層架構管理 Markdown 記憶文件。

### 三種執行模式

1. **Subprocess 模式** - wolf-chat 的 Python 子程序（優先實作）：`query_user`、`record_interaction`
2. **MCP 模式** - MCP Server，任何工具皆可調用：主要包裝 `query`（語意查詢）
3. **CLI 模式** - 獨立命令列工具，人工操作記憶

---

## 技術棧

### 套件

```bash
pip install ollama mcp requests
```

### Ollama 客戶端（雙模式可選）

環境變數格式：
```bash
export OLLAMA_API_KEY=your_api_key
```

**模式 A：ollama 套件**
```python
import os
from ollama import Client

# Ollama Cloud
client = Client(
    host="https://ollama.com",
    headers={'Authorization': 'Bearer ' + os.environ.get('OLLAMA_API_KEY')}
)

# 本地 Ollama（http://localhost:11434）
client = Client()

response = client.chat('qwen3-coder-next:cloud', messages=[...])
```

**模式 B：requests 直接呼叫 Ollama HTTP API**
```python
import os
import requests

OLLAMA_HOST = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
OLLAMA_API_KEY = os.environ.get('OLLAMA_API_KEY', '')

headers = {}
if OLLAMA_API_KEY:
    headers['Authorization'] = f'Bearer {OLLAMA_API_KEY}'

response = requests.post(
    f'{OLLAMA_HOST}/api/chat',
    headers=headers,
    json={
        'model': 'qwen3-coder-next:cloud',
        'messages': [...],
        'stream': True
    },
    stream=True
)
```

**settings.py 可選設定：**（位於 `wolf_memory/settings.py`，避免與 wolf-chat auto-generated `config.py` 混淆）
```python
LLM_BACKEND = 'ollama'    # 'ollama' | 'requests'
OLLAMA_HOST = 'http://localhost:11434'
OLLAMA_MODEL = 'qwen3-coder-next:cloud'
```

---

## 設計決策（已確認）

| 項目 | 決策 |
|------|------|
| 記憶儲存格式 | Markdown 文件 |
| AI 模型預設值 | `qwen3-coder-next:cloud` |
| 模型可調整性 | 作為 Wolf Chat 工具時，透過 `Setup.py` 設定 |
| MCP 框架 | 使用 `mcp` 套件 |
| 記憶操作 | 查詢、新增、更新/整理（完整 CRUD） |
| LLM 輸出方式 | 串流，偵測到 tool use 字段立即執行，不等輸出結束 |
| Tool Use | LLM 在運作中透過 tool call 傳遞資料，程式端即時攔截處理 |
| `query_user` 回傳 | 結構化資料，由 wolf-chat 端決定如何使用 |
| `record_interaction` 處理 | 接收到資料直接同步處理後回應 |
| 新用戶處理 | 自動建立空文件，回傳 `found: false` |

---

## wolf-chat 整合基礎流程

```
Wolf-Chat                          Wolf-Memory (subprocess)
    │                                   │
    │  1. query_user(username)          │
    │──────────────────────────────────►│
    │                                   │  查詢 MD 文件
    │  2. 結構化記憶資料                 │
    │◄──────────────────────────────────│
    │                                   │
    │  [Wolf-Chat 進行 LLM 對話]        │
    │                                   │
    │  3. record_interaction(           │
    │       username,                   │
    │       user_input,                 │
    │       bot_output)                 │
    │──────────────────────────────────►│
    │                                   │  寫入記憶文件
    │  4. ok                            │
    │◄──────────────────────────────────│
```

---

## API 定義

### Subprocess 通訊格式（JSON over stdin/stdout）

```json
Request:  { "action": "...", "params": { ... } }
Response: { "status": "ok" | "error", "data": { ... }, "error": "..." }
```

---

### 核心 API（wolf-chat 整合，優先實作）

#### `query_user`
對話開始前呼叫，回傳結構化資料給 wolf-chat 端處理。

```json
Request:
{
  "action": "query_user",
  "params": { "username": "PlayerAlpha" }
}

Response（有資料）:
{
  "status": "ok",
  "data": {
    "username": "PlayerAlpha",
    "found": true,
    "profile": {
      "tags": ["alliance", "trader"],
      "summary": "PlayerAlpha 的核心人物檔案摘要..."
    },
    "recent_interactions": [
      {
        "timestamp": "2026-04-01T08:00:00",
        "user_input": "...",
        "bot_output": "..."
      }
    ]
  }
}

Response（新用戶，已自動建立空文件）:
{
  "status": "ok",
  "data": {
    "username": "PlayerAlpha",
    "found": false
  }
}
```

#### `record_interaction`
wolf-chat 輸出完成後呼叫，接收到資料直接同步處理後回應。

wolf-chat 傳入**結構化資料**（不是 log 字串），分開傳 thoughts 和 dialogue。
`bot_thoughts` 包含 LLM 對情境的解讀，比純對話更有記憶價值，直接存入 working 層。

```json
Request:
{
  "action": "record_interaction",
  "params": {
    "username": "Pau Paw 파우",
    "timestamp": "2026-03-29T14:00:55",
    "user_input": "wolfy",
    "bot_thoughts": "User said 'wolfy' as a casual follow-up after position removal. Responding with playful banter.",
    "bot_output": "Heyyy, what's up? Miss me already?~ uwu"
  }
}

Response:
{
  "status": "ok",
  "data": {}
}
```

**working 層存入格式：**
```markdown
---
layer: working
entity: Pau Paw 파우
created_at: 2026-03-29T14:00:55
---

**User:** wolfy
**Thoughts:** User said 'wolfy' as a casual follow-up after position removal.
**Bot:** Heyyy, what's up? Miss me already?~ uwu
```

**wolf-chat 端需要修改的部分：**
- 對話完成後，從現有資料中取出 `username`、`timestamp`、`user_input`、`bot_thoughts`、`bot_output`，組成結構化 JSON 傳給 wolf-memory subprocess
- 不再直接寫 log 給記憶系統，log 檔維持現有格式不動

---

#### `query`（核心 AI 語意查詢）
純自然語言輸入，驅動內建 LLM 透過 tool use 查詢文件後回答。
回應語言跟隨 `input` 的語言。
**此 action 將以 MCP tool 包裝**，wolf-chat 或任何工具皆可透過 MCP 調用。

```json
Request:
{
  "action": "query",
  "params": {
    "input": "這個玩家之前有沒有提過他的聯盟？",
    "username": "Pau Paw 파우"   // 可選，有則縮小查詢範圍至該用戶；無則全域搜尋
  }
}

Response:
{
  "status": "ok",
  "data": {
    "answer": "根據記憶，Pau Paw 在 3/20 提過他屬於 R5 聯盟...",
    "sources": ["core/pau_paw.md", "episodic/2026-03-20_alliance.md"]
  }
}
```

**內部流程：**
```
收到 query
    │
    ▼
LLM 串流啟動（input 作為問題）
    │
    ├─ tool_call: list_files(entity="Pau Paw 파우")  // 有 username 時縮範圍
    ├─ tool_call: read_file("core/pau_paw.md")
    ├─ tool_call: read_file("episodic/...")
    │
    └─ LLM 整理輸出 answer（語言跟隨 input）+ sources
```

---

### 預留 API（CLI 用，先定義不實作）

| action | 用途 | 關鍵參數 |
|--------|------|----------|
| `list` | 列出記憶文件清單 | `layer?`, `username?` |
| `read` | 讀取特定文件全文 | `file_path` |
| `write` | 直接新增記憶文件 | `layer`, `username?`, `content` |
| `update` | 更新現有記憶文件 | `file_path`, `content` |
| `consolidate` | AI 整理/壓縮記憶 | `username?`, `layer?` |

---

## 記憶分層架構

### 四層文件結構

```
memories/
├── INDEX.json     # 快速查詢索引（見下方說明）
│
├── core/          # Layer 1：核心（永久人物檔案、關鍵事實）
├── episodic/      # Layer 2：情節（具體事件、有時間戳）
├── working/       # Layer 3：工作（近期對話，定期由 AI 壓縮進上層）
└── knowledge/     # Layer 4：知識（遊戲機制、靜態參考，人工維護）
```

| 層級 | 用途 | 生命週期 | 更新頻率 |
|------|------|----------|----------|
| core | 人物永久檔案、關鍵事實 | 永久 | 低 |
| episodic | 具體事件、有時序的記憶 | 長期 | 中 |
| working | 近期對話、暫存資訊 | 短期 | 高 |
| knowledge | 遊戲知識、靜態參考 | 永久 | 極低 |

### INDEX.json（快速查詢索引）

避免每次查詢掃描所有文件，新增/更新文件時自動維護。

```json
{
  "version": 1,
  "updated_at": "2026-04-01T00:00:00",
  "entities": {
    "PlayerAlpha": {
      "core": "core/player_alpha.md",
      "episodic": ["episodic/2026-04-01_alpha_trade.md"],
      "working": ["working/2026-04-01_session.md"],
      "tags": ["alliance", "trader"]
    }
  },
  "tags": {
    "alliance": ["core/player_alpha.md"],
    "combat": ["episodic/2026-03-25_battle.md"]
  }
}
```

### MD 文件格式（YAML frontmatter）

```markdown
---
id: player_alpha_core
layer: core
entity: PlayerAlpha
tags: [alliance, trader, friendly]
created_at: 2026-03-15T10:00:00
updated_at: 2026-04-01T08:30:00
summary: PlayerAlpha 的核心人物檔案
---

# PlayerAlpha

## 基本資料
- 聯盟：...
- 態度：友善

## 關鍵事件
- 2026-03-15：首次接觸，要求互不攻擊
```

---

## LLM Tool Use 架構（記憶工具內部）

wolf-memory 內部的 AI 處理（如 `consolidate`）使用串流 + 即時 tool call 攔截：

```
Ollama 串流輸出
    │
    ▼
StreamParser（逐 token 掃描）
    │
    ├─ 偵測到 tool_call ──► 立即執行對應文件操作（非同步）
    │                              │
    │                        讀/寫 MD + 更新 INDEX
    │                              │
    │                        回傳結果給 LLM（tool result）
    │
    └─ 一般文字 ──► 輸出給呼叫端
```

### LLM 內部可呼叫的文件操作 Tools

| Tool | 功能 | 參數 |
|------|------|------|
| `list_files` | 列出符合條件的文件路徑 | `layer?`, `entity?`, `tags?` |
| `read_file` | 讀取特定文件內容 | `file_path` |
| `write_file` | 新增文件 | `layer`, `entity?`, `tags`, `content`, `summary` |
| `update_file` | 更新現有文件 | `file_path`, `content` |

---

## 專案結構

```
wolf-memory/
├── NOTES.md
├── requirements.txt
├── server.py                   # 統一入口（--mode subprocess/cli/mcp）
│
├── wolf_memory/
│   ├── __init__.py
│   ├── settings.py             # model、memories 路徑等設定
│   ├── storage.py              # MD 文件讀寫
│   ├── index_manager.py        # INDEX.json 維護與快速查詢
│   ├── tools.py                # LLM 內部文件操作 tool 定義與執行
│   ├── stream_parser.py        # 串流攔截、即時 tool call 執行
│   ├── core.py                 # Ollama 整合（query_user / record / consolidate）
│   ├── subprocess_api.py       # Subprocess 模式（stdin/stdout JSON dispatcher）
│   ├── cli.py                  # CLI 模式入口（預留）
│   └── mcp_server.py           # MCP Server 模式入口（預留）
│
└── memories/
    ├── INDEX.json
    ├── core/
    ├── episodic/
    ├── working/
    └── knowledge/
```

---

## 開發順序

1. `storage.py` + `index_manager.py`（MD 讀寫 + INDEX 維護）
2. `tools.py`（LLM 內部文件操作 tools，純邏輯）
3. `stream_parser.py`（串流攔截 + 即時 tool call 執行）
4. `core.py`（Ollama 整合：query_user / record_interaction / consolidate）
5. `subprocess_api.py`（JSON dispatcher，對接 wolf-chat）
6. `server.py`（統一入口）
7. `cli.py` / `mcp_server.py`（預留介面）
8. 整合進 Wolf Chat `Setup.py`

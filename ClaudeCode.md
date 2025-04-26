# 專案架構及開發文檔

## 專案概述

Wolf Chat 是一個基於 MCP (Modular Capability Provider) 框架的聊天機器人助手，專為與遊戲 "Last War-Survival Game" 整合而設計。該機器人：

- 使用螢幕辨識技術監控遊戲聊天視窗
- 偵測包含 "wolf" 或 "Wolf" 關鍵字的聊天訊息
- 通過 LLM (語言模型) 生成回應
- 使用 UI 自動化技術將回應輸入到遊戲聊天介面

專案以英文編寫程式碼，但主要輸出和日誌以繁體中文顯示，方便使用者理解。

## 系統架構

### 核心元件

1. **主控模塊 (main.py)**
   - 協調各模塊的工作
   - 初始化 MCP 連接
     - **容錯處理**：即使 `config.py` 中未配置 MCP 伺服器，或所有伺服器連接失敗，程式現在也會繼續執行，僅打印警告訊息，MCP 功能將不可用。 (Added 2025-04-21)
   - 設置並管理主要事件循環
   - 處理程式生命週期管理和資源清理

2. **LLM 交互模塊 (llm_interaction.py)**
   - 與語言模型 API 通信
   - 管理系統提示與角色設定
   - 處理語言模型的工具調用功能
   - 格式化 LLM 回應
   - 提供工具結果合成機制

3. **UI 互動模塊 (ui_interaction.py)**
   - 使用圖像辨識技術監控遊戲聊天視窗
   - 檢測聊天泡泡與關鍵字
   - 複製聊天內容和獲取發送者姓名
   - 將生成的回應輸入到遊戲中

4. **MCP 客戶端模塊 (mcp_client.py)**
   - 管理與 MCP 服務器的通信
   - 列出和調用可用工具
   - 處理工具調用的結果和錯誤

5. **配置模塊 (config.py)**
   - 集中管理系統參數和設定
   - 整合環境變數
   - 配置 API 密鑰和服務器設定

6. **角色定義 (persona.json)**
   - 詳細定義機器人的人格特徵
   - 包含外觀、說話風格、個性特點等資訊
   - 提供給 LLM 以確保角色扮演一致性

7. **遊戲視窗監控模組 (game_monitor.py)** (取代 window-setup-script.py 和舊的 window-monitor-script.py)
   - 持續監控遊戲視窗 (`config.WINDOW_TITLE`)。
   - 確保視窗維持在設定檔 (`config.py`) 中指定的位置 (`GAME_WINDOW_X`, `GAME_WINDOW_Y`) 和大小 (`GAME_WINDOW_WIDTH`, `GAME_WINDOW_HEIGHT`)。
   - 確保視窗維持在最上層 (Always on Top)。
   - **定時遊戲重啟** (如果 `config.ENABLE_SCHEDULED_RESTART` 為 True)：
     - 根據 `config.RESTART_INTERVAL_MINUTES` 設定的間隔執行。
     - **簡化流程 (2025-04-25)**：
       1. 通過 `stdout` 向 `main.py` 發送 JSON 訊號 (`{'action': 'pause_ui'}`)，請求暫停 UI 監控。
       2. 等待固定時間（30 秒）。
       3. 調用 `restart_game_process` 函數，**嘗試**終止 (`terminate`/`kill`) `LastWar.exe` 進程（**無驗證**）。
       4. 等待固定時間（2 秒）。
       5. **嘗試**使用 `os.startfile` 啟動 `config.GAME_EXECUTABLE_PATH`（**無驗證**）。
       6. 等待固定時間（30 秒）。
       7. 使用 `try...finally` 結構確保**總是**執行下一步。
       8. 通過 `stdout` 向 `main.py` 發送 JSON 訊號 (`{'action': 'resume_ui'}`)，請求恢復 UI 監控。
     - **視窗調整**：遊戲視窗的位置/大小/置頂狀態的調整完全由 `monitor_game_window` 的主循環持續負責，重啟流程不再進行立即調整。
   - **作為獨立進程運行**：由 `main.py` 使用 `subprocess.Popen` 啟動，捕獲其 `stdout` (用於 JSON 訊號) 和 `stderr` (用於日誌)。
   - **進程間通信**：
     - `game_monitor.py` -> `main.py`：通過 `stdout` 發送 JSON 格式的 `pause_ui` 和 `resume_ui` 訊號。
     - **日誌處理**：`game_monitor.py` 的日誌被配置為輸出到 `stderr`，以保持 `stdout` 清潔，確保訊號傳遞可靠性。`main.py` 會讀取 `stderr` 並可能顯示這些日誌。
   - **生命週期管理**：由 `main.py` 在啟動時創建，並在 `shutdown` 過程中嘗試終止 (`terminate`)。

### 資料流程

```
[遊戲聊天視窗]
     ↑↓
[UI 互動模塊] <→ [圖像樣本庫]
     ↓
[主控模塊] ← [角色定義]
   ↑↓
[LLM 交互模塊] <→ [語言模型 API]
   ↑↓
[MCP 客戶端] <→ [MCP 服務器]
```

## 技術實現

### 核心功能實現

#### 聊天監控與觸發機制

系統使用基於圖像辨識的方法監控遊戲聊天界面：

1. **泡泡檢測（含 Y 軸優先配對）**：通過辨識聊天泡泡的左上角 (TL) 和右下角 (BR) 角落圖案定位聊天訊息。
    - **多外觀支援**：為了適應玩家可能使用的不同聊天泡泡外觀 (skin)，一般用戶泡泡的偵測機制已被擴充，可以同時尋找多組不同的角落模板 (例如 `corner_tl_type2.png`, `corner_br_type2.png` 等)。機器人泡泡目前僅偵測預設的角落模板。
    - **配對邏輯優化**：在配對 TL 和 BR 角落時，系統現在會優先選擇與 TL 角落 **Y 座標最接近** 的有效 BR 角落，以更好地區分垂直堆疊的聊天泡泡。
    - **偵測區域限制 (2025-04-21)**：為了提高效率並減少誤判，聊天泡泡角落（`corner_*.png`, `bot_corner_*.png`）的圖像辨識**僅**在螢幕的特定區域 `(150, 330, 600, 880)` 內執行。其他 UI 元素的偵測（如按鈕、關鍵字等）不受此限制。
2. **關鍵字檢測**：在泡泡區域內搜尋 "wolf" 或 "Wolf" 關鍵字圖像。
3. **內容獲取**：點擊關鍵字位置，使用剪貼板複製聊天內容。
4. **發送者識別（含氣泡重新定位與偏移量調整）**：**關鍵步驟** - 為了提高在動態聊天環境下的穩定性，系統在獲取發送者名稱前，會執行以下步驟：
    a. **初始偵測**：像之前一樣，根據偵測到的關鍵字定位觸發的聊天泡泡。
    b. **氣泡快照**：擷取該聊天泡泡的圖像快照。
    c. **重新定位**：在點擊頭像前，使用該快照在當前聊天視窗區域內重新搜尋氣泡的最新位置。
    d. **計算座標（新偏移量）**：
        - 如果成功重新定位氣泡，則根據找到的**新**左上角座標 (`new_tl_x`, `new_tl_y`)，應用新的偏移量計算頭像點擊位置：`x = new_tl_x - 45` (`AVATAR_OFFSET_X_REPLY`)，`y = new_tl_y + 10` (`AVATAR_OFFSET_Y_REPLY`)。
        - 如果無法重新定位（例如氣泡已滾動出畫面），則跳過此次互動，以避免點擊錯誤位置。
    e. **互動（含重試）**：
        - 使用計算出的（新的）頭像位置進行第一次點擊。
        - 檢查是否成功進入個人資料頁面 (`Profile_page.png`)。
        - **如果失敗**：系統會使用步驟 (b) 的氣泡快照，在聊天區域內重新定位氣泡，重新計算頭像座標，然後再次嘗試點擊。此過程最多重複 3 次。
        - **如果成功**（無論是首次嘗試還是重試成功）：繼續導航菜單，最終複製用戶名稱。
        - **如果重試後仍失敗**：放棄獲取該用戶名稱。
    f. **原始偏移量**：原始的 `-55` 像素水平偏移量 (`AVATAR_OFFSET_X`) 仍保留在程式碼中，用於其他不需要重新定位或不同互動邏輯的場景（例如 `remove_user_position` 功能）。
5. **防重複處理**：使用位置比較和內容歷史記錄防止重複回應。

#### LLM 整合

系統使用基於 OpenAI API 的介面與語言模型通信：

1. **模型選擇**：目前使用 `anthropic/claude-3.7-sonnet` 模型 (改進版)
2. **系統提示**：精心設計的提示確保角色扮演和功能操作
3. **工具調用**：支持模型使用 web_search 等工具獲取資訊
4. **工具處理循環**：實現了完整的工具調用、結果處理和續發邏輯
5. **結果合成**：添加了從工具調用結果合成回應的機制 (新增功能)

#### 多服務器連接

系統可以同時連接多個 MCP 服務器：

1. **並行初始化**：使用 asyncio 並行連接配置的所有服務器
2. **工具整合**：自動發現並整合各服務器提供的工具
3. **錯誤處理**：處理連接失敗和工具調用異常

### 異步架構

系統使用 Python 的 asyncio 作為核心異步框架：

1. **主事件循環**：處理 MCP 連接、LLM 請求和 UI 監控
2. **線程安全通信**：UI 監控在獨立線程中運行，通過線程安全隊列與主循環通信
3. **資源管理**：使用 AsyncExitStack 管理異步資源的生命週期
4. **清理機制**：實現了優雅的關閉和清理流程

### UI 自動化

系統使用多種技術實現 UI 自動化：

1. **圖像辨識**：使用 OpenCV 和 pyautogui 進行圖像匹配和識別。
2. **鍵鼠控制**：模擬鼠標點擊和鍵盤操作。
3. **剪貼板操作**：使用 pyperclip 讀寫剪貼板。
4. **狀態式處理**：基於 UI 狀態判斷的互動流程，確保操作穩定性。
5. **針對性回覆（上下文激活）**：
    - **時機**：在成功獲取發送者名稱並返回聊天介面後，但在將觸發資訊放入隊列傳遞給主線程之前。
    - **流程**：
        a. 再次使用氣泡快照重新定位觸發訊息的氣泡。
        b. 如果定位成功，點擊氣泡中心，並等待 0.25 秒（增加的延遲時間）以允許 UI 反應。
        c. 尋找並點擊彈出的「回覆」按鈕 (`reply_button.png`)。
        d. 如果成功點擊回覆按鈕，則設置一個 `reply_context_activated` 標記為 `True`。
        e. 如果重新定位氣泡失敗或未找到回覆按鈕，則該標記為 `False`。
    - **傳遞**：將 `reply_context_activated` 標記連同其他觸發資訊（發送者、內容、氣泡區域）一起放入隊列。
    - **發送**：主控模塊 (`main.py`) 在處理 `send_reply` 命令時，不再需要執行點擊回覆的操作，只需直接調用 `send_chat_message` 即可（因為如果 `reply_context_activated` 為 `True`，輸入框應已準備好）。

## 配置與部署

### 依賴項

主要依賴項目包括：
- openai: 與語言模型通信
- mcp: MCP 框架核心
- pyautogui, opencv-python: 圖像辨識與自動化
- pyperclip: 剪貼板操作
- pygetwindow: 窗口控制
- python-dotenv: 環境變數管理

### 環境設定

1. **API 設定**：通過 .env 文件或環境變數設置 API 密鑰
2. **MCP 服務器配置**：在 config.py 中配置要連接的 MCP 服務器
3. **UI 樣本**：需要提供特定遊戲界面元素的截圖模板
4. **遊戲視窗設定**：
   - 遊戲執行檔路徑 (`GAME_EXECUTABLE_PATH`)：用於未來可能的自動啟動功能。
   - 目標視窗位置與大小 (`GAME_WINDOW_X`, `GAME_WINDOW_Y`, `GAME_WINDOW_WIDTH`, `GAME_WINDOW_HEIGHT`)：由 `game_monitor.py` 使用。
   - 監控間隔 (`MONITOR_INTERVAL_SECONDS`)：`game_monitor.py` 檢查視窗狀態的頻率。

## 最近改進（2025-04-17）

### 工具調用與結果處理優化

針對使用工具時遇到的回應問題，我們進行了以下改進：

1. **模型切換**：
   - 已取消

2. **系統提示強化**：
   - 重寫系統提示，將角色人格與工具使用指南更緊密結合
   - 添加明確指示，要求 LLM 在工具調用後提供非空回應
   - 添加好與壞的示例，使模型更好地理解如何以角色方式融合工具信息

3. **工具結果處理機制**：
   - 實現了工具結果追蹤系統，保存所有工具調用結果
   - 添加了對非空回應的追蹤，確保能在多次循環間保持連續性
   - 開發了合成回應生成器，能從工具結果創建符合角色的回應

4. **回應解析改進**：
   - 重寫 `parse_structured_response` 函數，處理更多回應格式
   - 添加回應有效性檢測，確保只有有效回應才發送到遊戲
   - 強化 JSON 解析能力，更好地處理不完整或格式不標準的回應

5. **主程序流程優化**：
   - 修改了主流程中的回應處理邏輯，增加回應有效性檢查
   - 改進了工具調用循環處理，確保完整收集結果
   - 添加了更詳細的日誌記錄，方便排查問題

這些優化確保了即使在複雜工具調用後，Wolfhart 也能保持角色一致性，並提供合適的回應。無效回應不再發送到遊戲，提高了用戶體驗。

## 最近改進（2025-04-18）

### 支援多種一般聊天泡泡外觀，並修正先前錯誤配置

- **UI 互動模塊 (`ui_interaction.py`)**：
    - **修正**：先前錯誤地將多外觀支援應用於機器人泡泡。現已修正 `find_dialogue_bubbles` 函數，使其能夠載入並搜尋多組**一般用戶**泡泡的角落模板（例如 `corner_tl_type2.png`, `corner_br_type2.png` 等）。
    - 允許任何類型的一般用戶左上角與任何類型的一般用戶右下角進行配對，只要符合幾何條件。
    - 機器人泡泡的偵測恢復為僅使用預設的 `bot_corner_tl.png` 和 `bot_corner_br.png` 模板。
    - 這提高了對使用了自訂聊天泡泡外觀的**一般玩家**訊息的偵測能力。
- **模板文件**：
    - 在 `ui_interaction.py` 中為一般角落定義了新類型模板的路徑（`_type2`, `_type3`）。
    - **注意：** 需要在 `templates` 資料夾中實際添加對應的 `corner_tl_type2.png`, `corner_br_type2.png` 等圖片檔案才能生效。
- **文件更新 (`ClaudeCode.md`)**：
    - 在「技術實現」部分更新了泡泡檢測的說明。
    - 添加了此「最近改進」條目，並修正了先前的描述。

### 頭像點擊偏移量調整

- **UI 互動模塊 (`ui_interaction.py`)**：
    - 將 `AVATAR_OFFSET_X` 常數的值從 `-50` 調整為 `-55`。
    - 這統一了常規關鍵字觸發流程和 `remove_user_position` 功能中計算頭像點擊位置時使用的水平偏移量。
- **文件更新 (`ClaudeCode.md`)**：
    - 在「技術實現」的「發送者識別」部分強調了點擊位置是相對於觸發泡泡計算的，並註明了新的偏移量。
    - 添加了此「最近改進」條目。

### 聊天泡泡重新定位以提高穩定性

- **UI 互動模塊 (`ui_interaction.py`)**：
    - 在 `run_ui_monitoring_loop` 中，於偵測到關鍵字並成功複製文字後、獲取發送者名稱前，加入了新的邏輯：
        1. 擷取觸發氣泡的圖像快照。
        2. 使用 `pyautogui.locateOnScreen` 在聊天區域內重新尋找該快照的當前位置。
        3. 若找到，則根據**新位置**的左上角座標和新的偏移量 (`AVATAR_OFFSET_X_RELOCATED = -50`) 計算頭像點擊位置。
        4. 若找不到，則記錄警告並跳過此次互動。
    - 新增了 `AVATAR_OFFSET_X_RELOCATED` 和 `BUBBLE_RELOCATE_CONFIDENCE` 常數。
- **目的**：解決聊天視窗內容滾動後，原始偵測到的氣泡位置失效，導致點擊錯誤頭像的問題。透過重新定位，確保點擊的是與觸發訊息相對應的頭像。
- **文件更新 (`ClaudeCode.md`)**：
    - 更新了「技術實現」中的「發送者識別」部分，詳細說明了重新定位的步驟。
    - 在此「最近改進」部分添加了這個新條目。

### 互動流程優化 (頭像偏移、氣泡配對、針對性回覆)

- **UI 互動模塊 (`ui_interaction.py`)**：
    - **頭像偏移量調整**：修改了重新定位氣泡後計算頭像座標的邏輯，使用新的偏移量：左 `-45` (`AVATAR_OFFSET_X_REPLY`)，下 `+10` (`AVATAR_OFFSET_Y_REPLY`)。原始的 `-55` 偏移量 (`AVATAR_OFFSET_X`) 保留用於其他功能。
    - **氣泡配對優化**：修改 `find_dialogue_bubbles` 函數，使其在配對左上角 (TL) 和右下角 (BR) 時，優先選擇 Y 座標差異最小的 BR 角落，以提高垂直相鄰氣泡的區分度。
    - **頭像點擊重試**：修改 `retrieve_sender_name_interaction` 函數，增加了最多 3 次的重試邏輯。如果在點擊頭像後未能檢測到個人資料頁面，會嘗試重新定位氣泡並再次點擊。
    - **針對性回覆時機調整與延遲增加**：
        - 將點擊氣泡中心和回覆按鈕的操作移至成功獲取發送者名稱並返回聊天室之後、將觸發資訊放入隊列之前。
        - **增加了點擊氣泡中心後、尋找回覆按鈕前的等待時間至 0.25 秒**，以提高在 UI 反應較慢時找到按鈕的成功率。
        - 在放入隊列的數據中增加 `reply_context_activated` 標記，指示是否成功激活了回覆上下文。
        - 簡化了處理 `send_reply` 命令的邏輯，使其僅負責發送消息。
    - **氣泡快照保存 (用於除錯)**：在偵測到關鍵字後，擷取用於重新定位的氣泡圖像快照 (`bubble_snapshot`) 時，會將此快照保存到 `debug_screenshots` 文件夾中，檔名格式為 `debug_relocation_snapshot_X.png` (X 為 1 到 5 的循環數字)。這取代了先前僅保存氣泡區域截圖的邏輯。
- **目的**：
    - 進一步提高獲取發送者名稱的穩定性。
    - 改善氣泡配對的準確性。
    - 調整針對性回覆的流程，使其更符合邏輯順序，並通過增加延遲提高可靠性。
    - 提供用於重新定位的實際圖像快照，方便除錯。
- **文件更新 (`ClaudeCode.md`)**：
    - 更新了「技術實現」中的「泡泡檢測」、「發送者識別」部分。
    - 更新了「UI 自動化」部分關於「針對性回覆」的說明，反映了新的時機、標記和增加的延遲。
    - 在此「最近改進」部分更新了這個匯總條目，以包含最新的修改（包括快照保存和延遲增加）。

### UI 監控暫停與恢復機制 (2025-04-18)

- **目的**：解決在等待 LLM 回應期間，持續的 UI 監控可能導致的不穩定性或干擾問題，特別是與 `remove_position` 等需要精確 UI 狀態的操作相關。
- **`ui_interaction.py`**：
    - 引入了全局（模塊級）`monitoring_paused_flag` 列表（包含一個布爾值）。
    - 在 `run_ui_monitoring_loop` 的主循環開始處檢查此標誌。若為 `True`，則循環僅檢查命令隊列中的 `resume` 命令並休眠，跳過所有 UI 偵測和觸發邏輯。
    - 在命令處理邏輯中添加了對 `pause` 和 `resume` 動作的處理，分別設置 `monitoring_paused_flag[0]` 為 `True` 或 `False`。
- **`ui_interaction.py` (進一步修改)**：
    - **修正命令處理邏輯**：修改了 `run_ui_monitoring_loop` 的主循環。現在，在每次迭代開始時，它會使用一個內部 `while True` 循環和 `command_queue.get_nowait()` 來**處理完隊列中所有待處理的命令**（包括 `pause`, `resume`, `send_reply`, `remove_position` 等）。
    - **狀態檢查後置**：只有在清空當前所有命令後，循環才會檢查 `monitoring_paused_flag` 的狀態。如果標誌為 `True`，則休眠並跳過 UI 監控部分；如果為 `False`，則繼續執行 UI 監控（畫面檢查、氣泡偵測等）。
    - **目的**：解決先前版本中 `resume` 命令可能導致 UI 線程過早退出暫停狀態，從而錯過緊隨其後的 `send_reply` 或 `remove_position` 命令的問題。確保所有來自 `main.py` 的命令都被及時處理。
- **`main.py`**：
    - （先前修改保持不變）在主處理循環 (`run_main_with_exit_stack` 的 `while True` 循環) 中：
        - 在從 `trigger_queue` 獲取數據後、調用 `llm_interaction.get_llm_response` **之前**，向 `command_queue` 發送 `{ 'action': 'pause' }` 命令。
        - 使用 `try...finally` 結構，確保在處理 LLM 回應（包括命令處理和發送回覆）**之後**，向 `command_queue` 發送 `{ 'action': 'resume' }` 命令，無論處理過程中是否發生錯誤。

### `remove_position` 穩定性改進 (使用快照重新定位) (2025-04-19)

- **目的**：解決 `remove_position` 命令因聊天視窗滾動導致基於舊氣泡位置計算座標而出錯的問題。
- **`ui_interaction.py` (`run_ui_monitoring_loop`)**：
    - 在觸發事件放入 `trigger_queue` 的數據中，額外添加了 `bubble_snapshot`（觸發氣泡的圖像快照）和 `search_area`（用於快照的搜索區域）。
- **`main.py`**：
    - 修改了處理 `remove_position` 命令的邏輯，使其從 `trigger_data` 中提取 `bubble_snapshot` 和 `search_area`，並將它們包含在發送給 `command_queue` 的命令數據中。
- **`ui_interaction.py` (`remove_user_position` 函數)**：
    - 修改了函數簽名，以接收 `bubble_snapshot` 和 `search_area` 參數。
    - 在函數執行開始時，使用傳入的 `bubble_snapshot` 和 `search_area` 調用 `pyautogui.locateOnScreen` 來重新定位觸發氣泡的當前位置。
    - 如果重新定位失敗，則記錄錯誤並返回 `False`。
    - 如果重新定位成功，則後續所有基於氣泡位置的計算（包括尋找職位圖標的搜索區域 `search_region` 和點擊頭像的座標 `avatar_click_x`, `avatar_click_y`）都將使用這個**新找到的**氣泡座標。
- **效果**：確保 `remove_position` 操作基於氣泡的最新位置執行，提高了在動態滾動的聊天界面中的可靠性。

### 修正 Type3 關鍵字辨識並新增 Type4 支援 (2025-04-19)

- **目的**：修復先前版本中 `type3` 關鍵字辨識的錯誤，並擴充系統以支援新的 `type4` 聊天泡泡外觀和對應的關鍵字樣式。
- **`ui_interaction.py`**：
    - **修正 `find_keyword_in_region`**：移除了錯誤使用 `type2` 模板鍵來尋找 `type3` 關鍵字的重複程式碼，確保 `type3` 關鍵字使用正確的模板 (`keyword_wolf_lower_type3`, `keyword_wolf_upper_type3`)。
    - **新增 `type4` 泡泡支援**：
        - 在檔案開頭定義了 `type4` 角落模板的路徑常數 (`CORNER_TL_TYPE4_IMG`, `CORNER_BR_TYPE4_IMG`)。
        - 在 `find_dialogue_bubbles` 函數中，將 `type4` 的模板鍵 (`corner_tl_type4`, `corner_br_type4`) 加入 `regular_tl_keys` 和 `regular_br_keys` 列表。
        - 在 `run_ui_monitoring_loop` 的 `templates` 字典中加入了對應的鍵值對。
    - **新增 `type4` 關鍵字支援**：
        - 在檔案開頭定義了 `type4` 關鍵字模板的路徑常數 (`KEYWORD_wolf_LOWER_TYPE4_IMG`, `KEYWORD_Wolf_UPPER_TYPE4_IMG`)。
        - 在 `find_keyword_in_region` 函數中，加入了尋找 `type4` 關鍵字模板 (`keyword_wolf_lower_type4`, `keyword_wolf_upper_type4`) 的邏輯。
        - 在 `run_ui_monitoring_loop` 的 `templates` 字典中加入了對應的鍵值對。
- **效果**：提高了對 `type3` 關鍵字的辨識準確率，並使系統能夠辨識 `type4` 的聊天泡泡和關鍵字（前提是提供了對應的模板圖片）。

### 新增 Reply 關鍵字偵測與點擊偏移 (2025-04-20)

- **目的**：擴充關鍵字偵測機制，使其能夠辨識特定的回覆指示圖片 (`keyword_wolf_reply.png` 及其 type2, type3, type4 變體)，並在點擊這些特定圖片以複製文字時，應用 Y 軸偏移。
- **`ui_interaction.py`**：
    - **新增模板**：定義了 `KEYWORD_WOLF_REPLY_IMG` 系列常數，並將其加入 `run_ui_monitoring_loop` 中的 `templates` 字典。
    - **擴充偵測**：修改 `find_keyword_in_region` 函數，加入對 `keyword_wolf_reply` 系列模板的搜尋邏輯。
    - **條件式偏移**：在 `run_ui_monitoring_loop` 中，於偵測到關鍵字後，加入判斷邏輯。如果偵測到的關鍵字是 `keyword_wolf_reply` 系列之一，則：
        1. 計算用於 `copy_text_at` 的點擊座標時，Y 座標會增加 15 像素。
        2. 在後續嘗試激活回覆上下文時，計算用於點擊**氣泡中心**的座標時，Y 座標**也會**增加 15 像素。
    - 其他關鍵字或 UI 元素的點擊不受影響。
- **效果**：系統現在可以偵測新的回覆指示圖片作為觸發條件。當由這些圖片觸發時，用於複製文字的點擊和用於激活回覆上下文的氣泡中心點擊都會向下微調 15 像素，以避免誤觸其他 UI 元素。

### 強化 LLM 上下文處理與回應生成 (2025-04-20)

- **目的**：解決 LLM 可能混淆歷史對話與當前訊息，以及在回應中包含歷史記錄的問題。確保 `dialogue` 欄位只包含針對最新用戶訊息的新回覆。
- **`llm_interaction.py`**：
    - **修改 `get_system_prompt`**：
        - 在 `dialogue` 欄位的規則中，明確禁止包含任何歷史記錄，並強調必須只回應標記為 `<CURRENT_MESSAGE>` 的最新訊息。
        - 在核心指令中，要求 LLM 將分析和回應生成完全集中在 `<CURRENT_MESSAGE>` 標記的訊息上。
        - 新增了對 `<CURRENT_MESSAGE>` 標記作用的說明。
    - **修改 `_build_context_messages`**：
        - 在構建發送給 LLM 的訊息列表時，將歷史記錄中的最後一條用戶訊息用 `<CURRENT_MESSAGE>...</CURRENT_MESSAGE>` 標籤包裹起來。
        - 其他歷史訊息保持原有的 `[timestamp] speaker: message` 格式。
- **效果**：通過更嚴格的提示和明確的上下文標記，引導 LLM 準確區分當前互動和歷史對話，預期能提高回應的相關性並防止輸出冗餘的歷史內容。

### 強化 System Prompt 以鼓勵工具使用 (2025-04-19)

- **目的**：調整 `llm_interaction.py` 中的 `get_system_prompt` 函數，使其更明確地引導 LLM 在回應前主動使用工具（特別是記憶體工具）和整合工具資訊。
- **修改內容**：
    1.  **核心身份強化**：在 `CORE IDENTITY AND TOOL USAGE` 部分加入新的一點，強調 Wolfhart 會主動查閱內部知識圖譜和外部來源。
    2.  **記憶體指示強化**：將 `Memory Management (Knowledge Graph)` 部分的提示從 "IMPORTANT" 改為 "CRITICAL"，並明確指示在回應*之前*要考慮使用查詢工具檢查記憶體，同時也強調了寫入新資訊的主動性。
- **效果**：旨在提高 LLM 使用工具的主動性和依賴性，使其回應更具上下文感知和資訊準確性，同時保持角色一致性。

### 聊天歷史記錄上下文與日誌記錄 (2025-04-20)

- **目的**：
    1.  為 LLM 提供更豐富的對話上下文，以生成更連貫和相關的回應。
    2.  新增一個可選的聊天日誌功能，用於調試和記錄。
- **`main.py`**：
    - 引入 `collections.deque` 來儲存最近的對話歷史（用戶訊息和機器人回應），上限為 50 條。
    - 在調用 `llm_interaction.get_llm_response` 之前，將用戶訊息添加到歷史記錄中。
    - 在收到有效的 LLM 回應後，將機器人回應添加到歷史記錄中。
    - 新增 `log_chat_interaction` 函數，該函數：
        - 檢查 `config.ENABLE_CHAT_LOGGING` 標誌。
        - 如果啟用，則在 `config.LOG_DIR` 指定的文件夾中創建或附加到以日期命名的日誌文件 (`YYYY-MM-DD.log`)。
        - 記錄包含時間戳、發送者（用戶/機器人）、發送者名稱和訊息內容的條目。
    - 在收到有效 LLM 回應後調用 `log_chat_interaction`。
- **`llm_interaction.py`**：
    - 修改 `get_llm_response` 函數簽名，接收 `current_sender_name` 和 `history` 列表，而不是單個 `user_input`。
    - 新增 `_build_context_messages` 輔助函數，該函數：
        - 根據規則從 `history` 中篩選和格式化訊息：
            - 包含與 `current_sender_name` 相關的最近 4 次互動（用戶訊息 + 機器人回應）。
            - 包含來自其他發送者的最近 2 條用戶訊息。
        - 按時間順序排列選定的訊息。
        - 將系統提示添加到訊息列表的開頭。
    - 在 `get_llm_response` 中調用 `_build_context_messages` 來構建發送給 LLM API 的 `messages` 列表。
- **`config.py`**：
    - 新增 `ENABLE_CHAT_LOGGING` (布爾值) 和 `LOG_DIR` (字符串) 配置選項。
- **效果**：
    - LLM 現在可以利用最近的對話歷史來生成更符合上下文的回應。
    - 可以選擇性地將所有成功的聊天互動記錄到按日期組織的文件中，方便日後分析或調試。

### 整合 Wolfhart Memory Integration 協議至系統提示 (2025-04-22)

- **目的**：將使用者定義的 "Wolfhart Memory Integration" 記憶體存取協議整合至 LLM 的系統提示中，以強制執行更一致的上下文管理策略。
- **`llm_interaction.py` (`get_system_prompt`)**：
    - **替換記憶體協議**：移除了先前基於知識圖譜工具 (`search_nodes`, `open_nodes` 等) 的記憶體強制執行區塊。
    - **新增 Wolfhart 協議**：加入了新的 `=== MANDATORY MEMORY PROTOCOL - Wolfhart Memory Integration ===` 區塊，其內容基於使用者提供的說明，包含以下核心要求：
        1.  **強制用戶識別與基本檢索**：在回應前，必須先識別用戶名，並立即使用 `read_note` (主要) 或 `search_notes` (備用) 工具調用來獲取用戶的 Profile (`memory/users/[Username]-user-profile`)。
        2.  **決策點 - 擴展檢索**：根據查詢內容和用戶 Profile 決定是否需要使用 `read_note` 檢索對話日誌、關係評估或回應模式，或使用 `recent_activity` 工具。
        3.  **實施指南**：強調必須先檢查 Profile，使用正確的工具，以用戶偏好語言回應，且絕不向用戶解釋此內部流程。
        4.  **工具優先級**：明確定義了內部工具使用的優先順序：`read_note` > `search_notes` > `recent_activity`。
- **效果**：預期 LLM 在回應前會更穩定地執行記憶體檢索步驟，特別是強制性的用戶 Profile 檢查，從而提高回應的上下文一致性和角色扮演的準確性。

### 遊戲監控與定時重啟穩定性改進 (2025-04-25)

- **目的**：解決 `game_monitor.py` 在執行定時重啟時，可能出現遊戲未成功關閉/重啟，且 UI 監控未恢復的問題。
- **`game_monitor.py` (第一階段修改)**：
    - **日誌重定向**：將所有 `logging` 輸出重定向到 `stderr`，確保 `stdout` 只用於傳輸 JSON 訊號 (`pause_ui`, `resume_ui`) 給 `main.py`，避免訊號被日誌干擾。
    - **終止驗證**：在 `restart_game_process` 中，嘗試終止遊戲進程後，加入循環檢查（最多 10 秒），使用 `psutil.pid_exists` 確認進程確實已結束。
    - **啟動驗證**：在 `restart_game_process` 中，嘗試啟動遊戲後，使用循環檢查（最多 90 秒），調用 `find_game_window` 確認遊戲視窗已出現，取代固定的等待時間。
    - **立即調整嘗試**：在 `perform_scheduled_restart` 中，於成功驗證遊戲啟動後，立即嘗試調整一次視窗位置/大小/置頂。
    - **保證恢復訊號**：在 `perform_scheduled_restart` 中，使用 `try...finally` 結構包裹遊戲重啟邏輯，確保無論重啟成功與否，都會嘗試通過 `stdout` 發送 `resume_ui` 訊號給 `main.py`。
- **`game_monitor.py` (第二階段修改 - 簡化)**：
    - **移除驗證與立即調整**：根據使用者回饋，移除了終止驗證、啟動驗證以及立即調整視窗的邏輯。
    - **恢復固定等待**：重啟流程恢復使用固定的 `time.sleep()` 等待時間。
    - **發送重啟完成訊號**：在重啟流程結束後，發送 `{'action': 'restart_complete'}` JSON 訊號給 `main.py`。
- **`main.py`**：
    - **轉發重啟完成訊號**：`read_monitor_output` 線程接收到 `game_monitor.py` 的 `{'action': 'restart_complete'}` 訊號後，將 `{'action': 'handle_restart_complete'}` 命令放入 `command_queue`。
- **`ui_interaction.py`**：
    - **內部處理重啟完成**：`run_ui_monitoring_loop` 接收到 `{'action': 'handle_restart_complete'}` 命令後，在 UI 線程內部執行：
        1. 暫停 UI 監控。
        2. 等待固定時間（30 秒），讓遊戲啟動並穩定。
        3. 恢復 UI 監控並重置狀態（清除 `recent_texts` 和 `last_processed_bubble_info`）。
- **效果**：將暫停/恢復 UI 監控的時序控制權移至 `ui_interaction.py` 內部，減少了模塊間的直接依賴和潛在干擾，依賴持續監控來確保最終視窗狀態。

## 開發建議

### 優化方向

1. **UI 辨識強化**：
   - 改進泡泡匹配算法，提高可靠性
   - 添加文字 OCR 功能，減少依賴剪貼板
   - 擴展關鍵字檢測能力

2. **LLM 進一步優化**：
   - 繼續微調系統提示，平衡角色扮演與工具使用
   - 研究可能的上下文壓縮技術，處理長對話歷史
   - 為更多查詢類型添加專門的結果處理邏輯

3. **系統穩定性**：
   - 擴展錯誤處理和復原機制
   - 添加自動重啟和診斷功能
   - 實現更多遙測和監控功能

4. **對話能力增強**：
   - 實現對話歷史記錄
   - 添加主題識別與記憶功能
   - 探索多輪對話中的上下文理解能力

### 注意事項

1. **圖像模板**：確保所有必要的 UI 元素模板都已截圖並放置在 templates 目錄
2. **API 密鑰**：保護 API 密鑰安全，不要將其提交到版本控制系統
3. **窗口位置**：UI 自動化對窗口位置和大小敏感，保持一致性
4. **LLM 模型選擇**：在更改模型前測試其在工具調用方面的表現

## 分析與反思

### 架構優勢

1. **模塊化設計**：各功能區域職責明確，易於維護和擴展
2. **基於能力的分離**：MCP 框架提供良好的工具擴展性
3. **非侵入式整合**：不需要修改遊戲本身，通過 UI 自動化實現整合
4. **錯誤處理分層**：在多個層次實現錯誤處理，提高系統穩定性

### 潛在改進

1. **更穩健的 UI 互動**：當前的圖像辨識方法可能受游戲界面變化影響
2. **擴展觸發機制**：增加更多觸發條件，不僅限於關鍵字
3. **對話記憶**：實現對話歷史記錄，使機器人可以參考之前的互動
4. **多語言支持**：增強對不同語言的處理能力
5. **模型適應性**：開發更通用的提示和處理機制，適應不同的LLM模型

## 使用指南

### 快捷鍵 (新增)

- **F7**: 清除最近已處理的對話紀錄 (`recent_texts` in `ui_interaction.py`)。這有助於在需要時強制重新處理最近的訊息。
- **F8**: 暫停/恢復腳本的主要功能（UI 監控、LLM 互動）。
    - **暫停時**: UI 監控線程會停止偵測新的聊天氣泡，主循環會暫停處理新的觸發事件。
    - **恢復時**: UI 監控線程會恢復偵測，並且會清除最近的對話紀錄 (`recent_texts`) 和最後處理的氣泡資訊 (`last_processed_bubble_info`)，以確保從乾淨的狀態開始。
- **F9**: 觸發腳本的正常關閉流程，包括關閉 MCP 連接和停止監控線程。

### 啟動流程

1. 確保遊戲已啟動且聊天介面可見
2. 配置必要的 API 密鑰和服務器連接
3. 運行 `python main.py` 啟動系統
4. 系統將自動監控聊天，偵測關鍵字並回應

### 日常維護

1. 定期檢查 API 密鑰有效性
2. 確保模板圖像與當前遊戲界面匹配
3. 監控日誌以檢測可能的問題
4. 定期檢查和備份 llm_debug.log 文件

### 故障排除

常見問題及解決方案：
1. **無法識別泡泡**: 更新模板圖像，調整 CONFIDENCE_THRESHOLD
2. **複製內容失敗**: 檢查點擊位置和遊戲界面一致性
3. **LLM 連接問題**: 驗證 API 密鑰和網絡連接
4. **MCP 服務器連接失敗**: 確認服務器配置正確並且運行中
5. **工具調用後無回應**: 檢查 llm_debug.log 文件，查看工具調用結果和解析過程

</file_content>

Now that you have the latest state of the file, try the operation again with fewer, more precise SEARCH blocks. For large files especially, it may be prudent to try to limit yourself to <5 SEARCH/REPLACE blocks at a time, then wait for the user to respond with the result of the operation before following up with another replace_in_file call to make additional edits.
(If you run into this error 3 times in a row, you may use the write_to_file tool as a fallback.)
</error><environment_details>
# VSCode Visible Files
ClaudeCode.md

# VSCode Open Tabs
state.py
ui_interaction.py
c:/Users/Bigspring/AppData/Roaming/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json
window-monitor-script.py
persona.json
config.py
main.py
llm_interaction.py
ClaudeCode.md
requirements.txt
.gitignore

# Current Time
4/20/2025, 5:18:24 PM (Asia/Taipei, UTC+8:00)

# Context Window Usage
81,150 / 1,048.576K tokens used (8%)

# Current Mode
ACT MODE
</environment_details>

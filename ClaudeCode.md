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

1.  **主控模塊 (main.py)**
    - 協調各模塊的工作
    - 初始化 MCP 連接
        - **容錯處理**：即使 `config.py` 中未配置 MCP 伺服器，或所有伺服器連接失敗，程式現在也會繼續執行，僅打印警告訊息，MCP 功能將不可用。 (Added 2025-04-21)
        - **伺服器子進程管理 (修正 2025-05-02)**：使用 `mcp.client.stdio.stdio_client` 啟動和連接 `config.py` 中定義的每個 MCP 伺服器。`stdio_client` 作為一個異步上下文管理器，負責管理其啟動的子進程的生命週期。
        - **Windows 特定處理 (修正 2025-05-02)**：在 Windows 上，如果 `pywin32` 可用，會註冊一個控制台事件處理程序 (`win32api.SetConsoleCtrlHandler`)。此處理程序主要用於輔助觸發正常的關閉流程（最終會調用 `AsyncExitStack.aclose()`），而不是直接終止進程。伺服器子進程的實際終止依賴於 `stdio_client` 上下文管理器在 `AsyncExitStack.aclose()` 期間的清理操作。
    - **記憶體系統初始化 (新增 2025-05-02)**：在啟動時調用 `chroma_client.initialize_memory_system()`，根據 `config.py` 中的 `ENABLE_PRELOAD_PROFILES` 設定決定是否啟用記憶體預載入。
    - 設置並管理主要事件循環
    - **記憶體預載入 (新增 2025-05-02)**：在主事件循環中，如果預載入已啟用，則在每次收到 UI 觸發後、調用 LLM 之前，嘗試從 ChromaDB 預先獲取用戶資料 (`get_entity_profile`)、相關記憶 (`get_related_memories`) 和潛在相關的機器人知識 (`get_bot_knowledge`)。
    - 處理程式生命週期管理和資源清理（通過 `AsyncExitStack` 間接管理 MCP 伺服器子進程的終止）

2.  **LLM 交互模塊 (llm_interaction.py)**
    - 與語言模型 API 通信
    - 管理系統提示與角色設定
        - **條件式提示 (新增 2025-05-02)**：`get_system_prompt` 函數現在接受預載入的用戶資料、相關記憶和機器人知識。根據是否有預載入數據，動態調整系統提示中的記憶體檢索協議說明。
    - 處理語言模型的工具調用功能
    - 格式化 LLM 回應
    - 提供工具結果合成機制

3.  **UI 互動模塊 (ui_interaction.py)**
    - 使用圖像辨識技術監控遊戲聊天視窗
    - 檢測聊天泡泡與關鍵字
    - 複製聊天內容和獲取發送者姓名
    - 將生成的回應輸入到遊戲中

4.  **MCP 客戶端模塊 (mcp_client.py)**
    - 管理與 MCP 服務器的通信
    - 列出和調用可用工具
    - 處理工具調用的結果和錯誤

5.  **配置模塊 (config.py)**
    - 集中管理系統參數和設定
    - 整合環境變數
    - 配置 API 密鑰和服務器設定

6.  **角色定義 (persona.json)**
    - 詳細定義機器人的人格特徵
    - 包含外觀、說話風格、個性特點等資訊
    - 提供給 LLM 以確保角色扮演一致性

7.  **遊戲管理器模組 (game_manager.py)** (取代舊的 `game_monitor.py`)
    - **核心類 `GameMonitor`**：封裝所有遊戲視窗監控、自動重啟和進程管理功能。
    - **由 `Setup.py` 管理**：
        - 在 `Setup.py` 的 "Start Managed Bot & Game" 流程中被實例化和啟動。
        - 在停止會話時由 `Setup.py` 停止。
        - 設定（如視窗標題、路徑、重啟間隔等）通過 `Setup.py` 傳遞，並可在運行時通過 `update_config` 方法更新。
    - **功能**：
        - 持續監控遊戲視窗 (`config.WINDOW_TITLE`)。
        - 確保視窗維持在設定檔中指定的位置和大小。
        - 確保視窗保持活躍（帶到前景並獲得焦點）。
        - **定時遊戲重啟**：根據設定檔中的間隔執行。
            - **回調機制**：重啟完成後，通過回調函數通知 `Setup.py`（例如，`restart_complete`），`Setup.py` 隨後處理機器人重啟。
        - **進程管理**：使用 `psutil`（如果可用）查找和終止遊戲進程。
        - **跨平台啟動**：使用 `os.startfile` (Windows) 或 `subprocess.Popen` (其他平台) 啟動遊戲。
    - **獨立運行模式**：`game_manager.py` 仍然可以作為獨立腳本運行 (類似舊的 `game_monitor.py`)，此時它會從 `config.py` 加載設定，並通過 `stdout` 發送 JSON 訊號。

8.  **ChromaDB 客戶端模塊 (chroma_client.py)** (新增 2025-05-02)
    - 處理與本地 ChromaDB 向量數據庫的連接和互動。
    - 提供函數以初始化客戶端、獲取/創建集合，以及查詢用戶資料、相關記憶和機器人知識。
    - 使用 `chromadb.PersistentClient` 連接持久化數據庫。

### 資料流程

```
[遊戲聊天視窗]
     ↑↓
[UI 互動模塊] <→ [圖像樣本庫 / bubble_colors.json]
     ↓
[主控模塊] ← [角色定義]
   ↑↓         ↑↓
[LLM 交互模塊] ← [ChromaDB 客戶端模塊] <→ [ChromaDB 數據庫]
   ↑↓
[MCP 客戶端] <→ [MCP 服務器]
```
*(資料流程圖已更新以包含 ChromaDB)*

## 技術實現

### 核心功能實現

#### 聊天監控與觸發機制

系統監控遊戲聊天界面以偵測觸發事件。主要方法包括：

1.  **泡泡檢測 (Bubble Detection)**：
    *   **主要方法 (可選，預設禁用)**：**基於顏色的連通區域分析 (Color-based Connected Components Analysis)**
        *   **原理**：在特定區域 `(150, 330, 600, 880)` 內截圖，轉換至 HSV 色彩空間，根據 `bubble_colors.json` 中定義的顏色範圍 (HSV Lower/Upper) 建立遮罩 (Mask)，透過形態學操作 (Morphological Closing) 去除噪點並填充空洞，最後使用 `cv2.connectedComponentsWithStats` 找出符合面積閾值 (Min/Max Area) 的連通區域作為聊天泡泡。
        *   **效能優化**：在進行顏色分析前，可將截圖縮放 (預設 `scale_factor=0.5`) 以減少處理像素量，提高速度。面積閾值會根據縮放比例自動調整。
        *   **配置**：不同泡泡類型（如一般用戶、機器人）的顏色範圍和面積限制定義在 `bubble_colors.json` 文件中。
        *   **啟用**：此方法預設**禁用**。若要啟用，需修改 `ui_interaction.py` 中 `DetectionModule` 類別 `__init__` 方法內的 `self.use_color_detection` 變數為 `True`。
    *   **備用/預設方法**：**基於模板匹配的角落配對 (Template Matching Corner Pairing)**
        *   **原理**：在特定區域 `(150, 330, 600, 880)` 內，通過辨識聊天泡泡的左上角 (TL) 和右下角 (BR) 角落圖案 (`corner_*.png`, `bot_corner_*.png`) 來定位聊天訊息。
        *   **多外觀支援**：支援多種一般用戶泡泡外觀 (skin)，可同時尋找多組不同的角落模板。機器人泡泡目前僅偵測預設模板。
        *   **配對邏輯**：優先選擇與 TL 角落 Y 座標最接近的有效 BR 角落進行配對。
    *   **方法選擇與回退**：
        *   若 `use_color_detection` 設為 `True`，系統會**優先嘗試**顏色檢測。
        *   如果顏色檢測成功並找到泡泡，則使用其結果。
        *   如果顏色檢測**失敗** (發生錯誤) 或**未找到任何泡泡**，系統會**自動回退**到模板匹配方法。
        *   若 `use_color_detection` 設為 `False`，則直接使用模板匹配方法。
2.  **關鍵字檢測 (Keyword Detection)**：在偵測到的泡泡區域內，使用模板匹配搜尋 "wolf" 或 "Wolf" 關鍵字圖像 (包括多種樣式，如 `keyword_wolf_lower_type2.png`, `keyword_wolf_reply.png` 等)。
3.  **內容獲取 (Content Retrieval)**：
    *   **重新定位**：在複製文字前，使用觸發時擷取的氣泡快照 (`bubble_snapshot`) 在螢幕上重新定位氣泡的當前位置。
    *   **計算點擊位置**：根據重新定位後的氣泡位置和關鍵字在其中的相對位置，計算出用於複製文字的精確點擊座標。如果偵測到的是特定回覆關鍵字 (`keyword_wolf_reply*`)，則 Y 座標會增加偏移量 (目前為 +25 像素)。
    *   **複製**：點擊計算出的座標，嘗試使用彈出菜單的 "複製" 選項或模擬 Ctrl+C 來複製聊天內容至剪貼板。
4.  **發送者識別 (Sender Identification)**：
    *   **重新定位**：再次使用氣泡快照重新定位氣泡。
    *   **計算頭像座標**：根據**新**找到的氣泡左上角座標，應用特定偏移量 (`AVATAR_OFFSET_X_REPLY`, `AVATAR_OFFSET_Y_REPLY`) 計算頭像點擊位置。
    *   **互動（含重試）**：點擊計算出的頭像位置，檢查是否成功進入個人資料頁面 (`Profile_page.png`)。若失敗，最多重試 3 次（每次重試前會再次重新定位氣泡）。若成功，則繼續導航菜單複製用戶名稱。
    *   **原始偏移量**：原始的 `-55` 像素水平偏移量 (`AVATAR_OFFSET_X`) 仍保留，用於 `remove_user_position` 等其他功能。
5.  **防重複處理 (Duplicate Prevention)**：使用最近處理過的文字內容歷史 (`recent_texts`) 防止對相同訊息重複觸發。

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

## 最近改進（2025-04-28）

### LLM 回應 JSON 輸出順序調整

- **目的**：調整 LLM 結構化回應的 JSON 輸出格式，將 `commands` 欄位移至最前方，接著是 `dialogue` 和 `thoughts`，以期改善後續處理流程或提高 LLM 對工具調用（tool_calls）與指令（commands）區分的清晰度。
- **`llm_interaction.py`**：
    - 修改了 `parse_structured_response` 函數中構建結果字典的順序。
    - 現在，當成功解析來自 LLM 的有效 JSON 時，輸出的字典鍵順序將優先排列 `commands`。
    - **效果**：標準化了 JSON 回應的結構順序，有助於下游處理，並可能間接幫助 LLM 更清晰地組織其輸出，尤其是在涉及工具調用和特定指令時。

## 最近改進（2025-05-01）

### 關鍵字檢測重構 (雙重方法 + 座標校正)

- **目的**：根據 "Wolf 關鍵詞檢測方法深度重構指南"，重構 `ui_interaction.py` 中的關鍵字檢測邏輯，以提高辨識穩定性並確保座標系統一致性。
- **`ui_interaction.py` (`DetectionModule`)**：
    - **新增雙重檢測方法 (`find_keyword_dual_method`)**：
        - 使用 OpenCV (`cv2.matchTemplate`) 進行模板匹配。
        - 同時在**灰度圖**和 **CLAHE 增強圖**上進行匹配，並處理**反相**情況 (`cv2.bitwise_not`)。
        - **座標校正**：`cv2.matchTemplate` 返回的座標是相對於截圖區域 (`region`) 的。在返回結果前，已將其轉換為絕對螢幕座標 (`absolute_x = region_x + relative_x`, `absolute_y = region_y + relative_y`)，以確保與 `pyautogui` 點擊座標一致。
        - **結果合併**：
            1.  優先選擇灰度與 CLAHE 方法結果**重合**且距離接近 (`MATCH_DISTANCE_THRESHOLD`) 的匹配。
            2.  若無重合，則選擇單一方法中置信度**非常高** (`DUAL_METHOD_HIGH_CONFIDENCE_THRESHOLD`) 的結果。
            3.  若仍無結果，則回退到單一方法中置信度**較高** (`DUAL_METHOD_FALLBACK_CONFIDENCE_THRESHOLD`) 的結果。
        - **核心模板**：僅使用三個核心模板 (`keyword_wolf_lower`, `keyword_Wolf_upper`, `keyword_wolf_reply`) 進行檢測。
        - **效能統計**：添加了計數器以追蹤檢測次數、成功率、各方法使用分佈、平均時間和反相匹配率 (`print_detection_stats` 方法)。
        - **除錯視覺化**：在高除錯級別 (`DEBUG_LEVEL >= 3`) 下，會保存預處理圖像和標記了檢測點的結果圖像。
    - **舊方法保留 (`_find_keyword_legacy`)**：原有的基於 `pyautogui.locateAllOnScreen` 和多模板的 `find_keyword_in_region` 邏輯被移至此私有方法，用於向後兼容或調試比較。
    - **包裝器方法 (`find_keyword_in_region`)**：現在作為一個包裝器，根據 `use_dual_method` 標誌（預設為 `True`）調用新的雙重方法或舊的 legacy 方法。
    - **初始化更新**：`__init__` 方法更新以支持 `use_dual_method` 標誌、CLAHE 初始化、核心模板提取和效能計數器。
- **`ui_interaction.py` (`run_ui_monitoring_loop`)**：
    - **模板字典**：初始化時區分 `essential_templates` 和 `legacy_templates`，並合併後傳遞給 `DetectionModule`。
    - **模塊實例化**：以 `use_dual_method=True` 實例化 `DetectionModule`。
- **效果**：預期能提高關鍵字檢測在不同光照、對比度或 UI 主題下的魯棒性，同時確保檢測到的座標能被 `pyautogui` 正確用於點擊。簡化了需要維護的關鍵字模板數量。

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

1.  **首次設定與配置工具 (Setup.py)**：
    *   執行 `python Setup.py` 啟動圖形化設定工具。
    *   **功能**：
        *   檢查 `config.py` 和 `.env` 文件是否存在。
        *   如果 `config.py` 不存在，使用 `config_template.py` 作為模板創建。
        *   如果 `.env` 不存在，提示用戶輸入 API 金鑰等敏感資訊並創建。
        *   提供多個標籤頁用於配置：
            *   **API Settings**: 設定 OpenAI/兼容 API 的 Base URL、API Key 和模型名稱。
            *   **MCP Servers**: 啟用/禁用和配置 Exa、Chroma 及自定義 MCP 伺服器。
            *   **Game Settings**: 配置遊戲視窗標題、執行檔路徑、位置、大小和自動重啟選項。
            *   **Memory Settings (新增 2025-05-02)**: 配置 ChromaDB 記憶體整合，包括啟用預載入、設定集合名稱（用戶資料、對話、機器人知識）和預載入記憶數量。
        *   提供按鈕以保存設定、安裝依賴項、運行主腳本 (`main.py`)、運行測試腳本 (`test/llm_debug_script.py`) 以及停止由其啟動的進程。
    *   **重要**：`.env` 文件應加入 `.gitignore`。`config.py` 通常也應加入 `.gitignore`。
2.  **API 設定**：API 金鑰和其他敏感資訊儲存在 `.env` 文件中，由 `config.py` 讀取。
3.  **核心配置 (config.py)**：包含非敏感的系統參數、MCP 伺服器列表、UI 模板路徑、遊戲視窗設定等。此文件現在由 `Setup.py` 根據 `config_template.py` 生成（如果不存在）。
4.  **MCP 服務器配置**：在 `config.py` 中配置要連接的 MCP 服務器。
5.  **UI 樣本**：需要提供特定遊戲界面元素的截圖模板，路徑在 `config.py` 中定義。
6.  **遊戲視窗設定**：在 `config.py` 中配置：
    *   遊戲執行檔路徑 (`GAME_EXECUTABLE_PATH`)。
    *   目標視窗位置與大小 (`GAME_WINDOW_X`, `GAME_WINDOW_Y`, `GAME_WINDOW_WIDTH`, `GAME_WINDOW_HEIGHT`)。
    *   監控間隔 (`MONITOR_INTERVAL_SECONDS`)。

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

### 關鍵字檢測重構 (雙重方法與座標校正) (2025-05-01)

- **目的**：提高關鍵字 ("wolf", "Wolf", 回覆指示符) 檢測的穩定性和對視覺變化的魯棒性，並確保檢測到的座標能準確對應 `pyautogui` 的點擊座標。
- **`ui_interaction.py` (`DetectionModule`)**：
    - **重構 `find_keyword_in_region`**：此方法現在作為一個包裝器 (wrapper)。
    - **新增 `find_keyword_dual_method`**：
        - 成為預設的關鍵字檢測方法 (由 `use_dual_method` 標誌控制，預設為 `True`)。
        - **核心邏輯**：
            1. 對目標區域截圖。
            2. 同時準備灰度 (grayscale) 和 CLAHE (對比度限制自適應直方圖均衡化) 增強的圖像版本。
            3. 對三種核心關鍵字模板 (`keyword_wolf_lower`, `keyword_Wolf_upper`, `keyword_wolf_reply`) 也進行灰度與 CLAHE 預處理。
            4. 使用 `cv2.matchTemplate` 分別在灰度圖和 CLAHE 圖上進行模板匹配 (包括正向和反向匹配 `cv2.bitwise_not`)。
            5. **座標校正**：將 `cv2.matchTemplate` 返回的 **相對** 於截圖區域的座標，通過加上截圖區域的左上角座標 (`region_x`, `region_y`)，轉換為 **絕對** 螢幕座標，確保與 `pyautogui` 使用的座標系統一致。
            6. **結果合併策略**：
                - 優先選擇灰度與 CLAHE 方法結果**重合** (中心點距離小於 `MATCH_DISTANCE_THRESHOLD`) 且置信度最高的匹配。
                - 若無重合，則回退到單一方法中置信度最高的匹配 (需高於特定閾值 `DUAL_METHOD_FALLBACK_CONFIDENCE_THRESHOLD`)。
        - **效能統計**：增加了計數器 (`performance_stats`) 來追蹤檢測總數、成功數、各方法成功數、反相匹配數和總耗時。新增 `print_detection_stats` 方法用於輸出統計。
        - **除錯增強**：在高除錯級別 (`DEBUG_LEVEL >= 3`) 下，會保存預處理圖像和標記了檢測結果的圖像。
    - **新增 `_find_keyword_legacy`**：包含原 `find_keyword_in_region` 的邏輯，使用 `pyautogui.locateAllOnScreen` 遍歷所有（包括已棄用的）關鍵字模板，用於向後兼容或除錯比較。
    - **常量整理**：將核心關鍵字模板標記為活躍，其他類型標記為棄用，並添加了 CLAHE 和雙重方法相關的新常量。
    - **初始化更新**：`__init__` 方法更新以支持新標誌、初始化 CLAHE 物件和效能計數器。
- **`ui_interaction.py` (`run_ui_monitoring_loop`)**：
    - 更新了 `templates` 字典的創建方式，區分核心模板和舊模板。
    - 在實例化 `DetectionModule` 時傳遞 `use_dual_method=True`。
- **效果**：預期能更可靠地在不同光照、對比度或顏色主題下檢測到關鍵字，同時確保點擊位置的準確性。

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

## 最近改進（2025-04-27）

### Setup.py 功能增強

- **目的**：增強 `Setup.py` 設定工具的功能，使其在保存設定後保持開啟，並提供直接啟動和終止 Chat Bot 及 Test 腳本的按鈕。
- **修改內容**：
    - 修改 `save_settings` 方法，移除關閉視窗的邏輯，僅顯示保存成功的提示訊息。
    - 在 GUI 底部新增 "Run Chat Bot" 和 "Run Test" 按鈕，分別用於啟動 `main.py` 和 `test/llm_debug_script.py`。
    - 新增 "Stop Process" 按鈕，用於終止由上述兩個按鈕啟動的腳本。
    - 實現進程追蹤和按鈕狀態管理，確保在有腳本運行時禁用運行按鈕，啟用停止按鈕。
- **效果**：提高了 `Setup.py` 的易用性，方便使用者在調整設定後直接啟動腳本進行測試，並提供了便捷的終止方式。

### llm_debug_script.py 功能增強

- **目的**：讓用戶在啟動時能夠輸入自己的名字。
- **修改內容**：
    - 新增了一個　`get_username()` 函數來提示用戶輸入名字
    - 在 `debug_loop()` 函數中，刪除了固定的 `user_name = "Debugger"` 行，並替換為從 `get_username()` 函數獲取名字的調用。
    - **新增 ChromaDB 初始化與數據預取**：
        - 在 `debug_loop()` 開始時導入 `chroma_client` 並調用 `initialize_chroma_client()`。
        - 在每次用戶輸入後、調用 `llm_interaction.get_llm_response` 之前，新增了調用 `chroma_client.get_entity_profile()` 和 `chroma_client.get_related_memories()` 的邏輯。
        - 將獲取的用戶資料和相關記憶作為參數傳遞給 `get_llm_response`。
- **效果**：修改後，腳本啟動時會提示用戶輸入自己的名字（預設為 'Debugger'）。它現在不僅會初始化 ChromaDB 連接，還會在每次互動前預先查詢用戶資料和相關記憶，並將這些資訊注入到發送給 LLM 的系統提示中，以便在測試期間更真實地模擬記憶體功能。

## 最近改進（2025-05-02）

### ChromaDB 客戶端初始化更新

- **目的**：更新 ChromaDB 客戶端初始化方式以兼容 ChromaDB v1.0.6+ 版本，解決舊版 `chromadb.Client(Settings(...))` 方法被棄用的問題。
- **`chroma_client.py`**：
    - 修改了 `initialize_chroma_client` 函數。
    - 將舊的初始化代碼：
      ```python
      _client = chromadb.Client(Settings(
          chroma_db_impl="duckdb+parquet",
          persist_directory=config.CHROMA_DATA_DIR
      ))
      ```
    - 替換為新的推薦方法：
      ```python
      _client = chromadb.PersistentClient(path=config.CHROMA_DATA_DIR)
      ```
- **效果**：腳本現在使用 ChromaDB v1.0.6+ 推薦的 `PersistentClient` 來連接本地持久化數據庫，避免了啟動時的 `deprecated configuration` 錯誤。

### ChromaDB 記憶體系統整合與優化

- **目的**：引入基於 ChromaDB 的向量記憶體系統，以提高回應速度和上下文連貫性，並提供可配置的記憶體預載入選項。
- **`Setup.py`**：
    - 新增 "Memory Settings" 標籤頁，允許用戶：
        - 啟用/禁用用戶資料預載入 (`ENABLE_PRELOAD_PROFILES`)。
        - 設定預載入的相關記憶數量 (`PRELOAD_RELATED_MEMORIES`)。
        - 配置 ChromaDB 集合名稱 (`PROFILES_COLLECTION`, `CONVERSATIONS_COLLECTION`, `BOT_MEMORY_COLLECTION`)。
    - 更新 `load_current_config`, `update_ui_from_data`, `save_settings` 和 `generate_config_file` 函數以處理這些新設定。
    - 修正了 `generate_config_file` 中寫入 ChromaDB 設定的邏輯，確保設定能正確保存到 `config.py`。
    - 修正了 `update_ui_from_data` 中的 `NameError`。
    - 將 "Profiles Collection" 的預設值更新為 "wolfhart_memory"，以匹配實際用法。
- **`config_template.py`**：
    - 添加了 ChromaDB 相關設定的佔位符。
- **`chroma_client.py`**：
    - 新增模塊，封裝 ChromaDB 連接和查詢邏輯。
    - 實現 `initialize_chroma_client`, `get_collection`, `get_entity_profile`, `get_related_memories`, `get_bot_knowledge` 函數。
    - 更新 `initialize_chroma_client` 以使用 `chromadb.PersistentClient`。
    - 修正 `get_entity_profile` 以使用 `query` 方法（而非 `get`）和正確的集合名稱 (`config.BOT_MEMORY_COLLECTION`) 來查找用戶資料。
- **`main.py`**：
    - 導入 `chroma_client`。
    - 添加 `initialize_memory_system` 函數，在啟動時根據配置初始化 ChromaDB。
    - 在主循環中，根據 `config.ENABLE_PRELOAD_PROFILES` 和 `config.PRELOAD_RELATED_MEMORIES` 設定，在調用 LLM 前預載入用戶資料、相關記憶和機器人知識。
    - 將預載入的數據傳遞給 `llm_interaction.get_llm_response`。
- **`llm_interaction.py`**：
    - 更新 `get_llm_response` 和 `get_system_prompt` 函數簽名以接收預載入的記憶體數據。
    - 修改 `get_system_prompt` 以：
        - 在提示中包含預載入的用戶資料、相關記憶和機器人知識（如果可用）。
        - 根據是否有預載入數據，動態調整記憶體檢索協議的說明（優化版 vs. 完整版）。
        - 修正了在禁用預載入時，基本用戶檢索範例中使用的集合名稱，使其與 `chroma_client.py` 一致 (`config.BOT_MEMORY_COLLECTION`)。
- **效果**：實現了可配置的記憶體預載入功能，預期能提高回應速度和質量。統一了各模塊中關於集合名稱和查詢邏輯的處理。

### MCP 伺服器子進程管理與 Windows 安全終止 (修正)

- **目的**：確保由 `main.py` 啟動的 MCP 伺服器（根據 `config.py` 配置）能夠在主腳本退出時（無論正常或異常）被可靠地終止，特別是在 Windows 環境下。
- **`main.py`**：
    - **恢復啟動方式**：`connect_and_discover` 函數恢復使用 `mcp.client.stdio.stdio_client` 來啟動伺服器並建立連接。這解決了先前手動管理子進程導致的 `AttributeError: 'StreamWriter' object has no attribute 'send'` 問題。
    - **依賴 `stdio_client` 進行終止**：不再手動管理伺服器子進程的 `Process` 對象。現在依賴 `stdio_client` 的異步上下文管理器 (`__aexit__` 方法) 在 `AsyncExitStack` 關閉時（於 `shutdown` 函數中調用 `exit_stack.aclose()` 時觸發）來處理其啟動的子進程的終止。
    - **保留 Windows 事件處理器**：
        - 仍然保留了 `windows_ctrl_handler` 函數和使用 `win32api.SetConsoleCtrlHandler` 註冊它的邏輯（如果 `pywin32` 可用）。
        - **注意**：此處理程序現在**不直接**終止 MCP 伺服器進程（因為 `mcp_server_processes` 字典不再被填充）。它的主要作用是確保在 Windows 上的各種退出事件（如關閉控制台窗口）能觸發 Python 的正常關閉流程，進而執行 `finally` 塊中的 `shutdown()` 函數，最終調用 `exit_stack.aclose()` 來讓 `stdio_client` 清理其子進程。
        - `terminate_all_mcp_servers` 函數雖然保留，但因 `mcp_server_processes` 為空而不會執行實際的終止操作。
    - **移除冗餘終止調用**：從 `shutdown` 函數中移除了對 `terminate_all_mcp_servers` 的直接調用，因為終止邏輯現在由 `exit_stack.aclose()` 間接觸發。
- **依賴項**：Windows 上的控制台事件處理仍然依賴 `pywin32` 套件。如果未安裝，程式會打印警告，關閉時的可靠性可能略有降低（但 `stdio_client` 的正常清理機制應在多數情況下仍然有效）。
- **效果**：恢復了與 `mcp` 庫的兼容性，同時通過標準的上下文管理和輔助性的 Windows 事件處理，實現了在主程式退出時關閉 MCP 伺服器子進程的目標。

## 最近改進（2025-05-12）

### 遊戲視窗置頂邏輯修改

- **目的**：將 `game_monitor.py` 中強制遊戲視窗「永遠在最上層」(Always on Top) 的行為，修改為「臨時置頂並獲得焦點」(Bring to Foreground/Activate)，以解決原方法僅覆蓋其他視窗的問題。
- **`game_monitor.py`**：
    - 在 `monitor_game_window` 函數的監控循環中，移除了使用 `win32gui.SetWindowPos` 和 `win32con.HWND_TOPMOST` 來檢查和設定 `WS_EX_TOPMOST` 樣式的程式碼。
    - 替換為檢查當前前景視窗 (`win32gui.GetForegroundWindow()`) 是否為目標遊戲視窗 (`hwnd`)。
    - 如果不是，則嘗試以下步驟將視窗帶到前景並獲得焦點：
        1.  使用 `win32gui.SetWindowPos` 搭配 `win32con.HWND_TOP` 旗標，將視窗提升到所有非最上層視窗之上。
        2.  呼叫 `win32gui.SetForegroundWindow(hwnd)` 嘗試將視窗設為前景並獲得焦點。
        3.  短暫延遲後，檢查視窗是否成功成為前景視窗。
        4.  如果 `SetForegroundWindow` 未成功，則嘗試使用 `pygetwindow` 庫提供的 `window.activate()` 方法作為備用方案。
    - 更新了相關的日誌訊息以反映新的行為和備用邏輯。
- **效果**：監控腳本現在會使用更全面的方法嘗試將失去焦點的遊戲視窗重新激活並帶到前景，包括備用方案，以提高在不同 Windows 環境下獲取焦點的成功率。這取代了之前僅強制視覺覆蓋的行為。

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

## 最近改進（2025-05-13）

### 遊戲監控模組重構

- **目的**：將遊戲監控功能從獨立的 `game_monitor.py` 腳本重構為一個更健壯、更易於管理的 `game_manager.py` 模組，並由 `Setup.py` 統一控制其生命週期和配置。
- **`game_manager.py` (新模組)**：
    - 創建了 `GameMonitor` 類，封裝了所有遊戲視窗監控、自動重啟和進程管理邏輯。
    - 提供了 `create_game_monitor` 工廠函數。
    - 支持通過構造函數和 `update_config` 方法進行配置。
    - 使用回調函數 (`callback`) 與調用者（即 `Setup.py`）通信，例如在遊戲重啟完成時。
    - 保留了獨立運行模式，以便在直接執行時仍能工作（主要用於測試或舊版兼容）。
    - 程式碼註解和日誌訊息已更新為英文。
    - **新增遊戲崩潰自動恢復 (2025-05-15)**：
        - 在 `_monitor_loop` 方法中，優先檢查遊戲進程 (`_is_game_running`) 是否仍在運行。
        - 如果進程消失，會記錄警告並嘗試重新啟動遊戲 (`_start_game_process`)。
        - 新增 `_is_game_running` 方法，使用 `psutil` 檢查具有指定進程名稱的遊戲是否正在運行。
- **`Setup.py` (修改)**：
    - 導入 `game_manager`。
    - 在 `WolfChatSetup` 類的 `__init__` 方法中初始化 `self.game_monitor = None`。
    - 在 `start_managed_session` 方法中：
        - 創建 `game_monitor_callback` 函數以處理來自 `GameMonitor` 的動作（特別是 `restart_complete`）。
        - 使用 `game_manager.create_game_monitor` 創建 `GameMonitor` 實例。
        - 啟動 `GameMonitor`。
    - 新增 `_handle_game_restart_complete` 方法，用於在收到 `GameMonitor` 的重啟完成回調後，處理機器人的重啟。
    - 在 `stop_managed_session` 方法中，調用 `self.game_monitor.stop()` 並釋放實例。
    - 修改 `_restart_game_managed` 方法，使其在 `self.game_monitor` 存在且運行時，調用 `self.game_monitor.restart_now()` 來執行遊戲重啟。
    - 在 `save_settings` 方法中，如果 `self.game_monitor` 實例存在，則調用其 `update_config` 方法以更新運行時配置。
- **`main.py` (修改)**：
    - 移除了所有對舊 `game_monitor.py` 的導入、子進程啟動、訊號讀取和生命週期管理相關的程式碼。遊戲監控現在完全由 `Setup.py` 在受管會話模式下處理。
- **舊檔案刪除**：
    - 刪除了原來的 `game_monitor.py` 文件。
- **效果**：
    - 遊戲監控邏輯更加內聚和模塊化。
    - `Setup.py` 現在完全控制遊戲監控的啟動、停止和配置，簡化了 `main.py` 的職責。
    - 通過回調機制實現了更清晰的模塊間通信。
    - 提高了程式碼的可維護性和可擴展性。

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

## 最近改進（2025-05-02）

### MCP 伺服器子進程管理與 Windows 安全終止 (修正)

- **目的**：確保由 `main.py` 啟動的 MCP 伺服器（根據 `config.py` 配置）能夠在主腳本退出時（無論正常或異常）被可靠地終止，特別是在 Windows 環境下。
- **`main.py`**：
    - **恢復啟動方式**：`connect_and_discover` 函數恢復使用 `mcp.client.stdio.stdio_client` 來啟動伺服器並建立連接。這解決了先前手動管理子進程導致的 `AttributeError: 'StreamWriter' object has no attribute 'send'` 問題。
    - **依賴 `stdio_client` 進行終止**：不再手動管理伺服器子進程的 `Process` 對象。現在依賴 `stdio_client` 的異步上下文管理器 (`__aexit__` 方法) 在 `AsyncExitStack` 關閉時（於 `shutdown` 函數中調用 `exit_stack.aclose()` 時觸發）來處理其啟動的子進程的終止。
    - **保留 Windows 事件處理器**：
        - 仍然保留了 `windows_ctrl_handler` 函數和使用 `win32api.SetConsoleCtrlHandler` 註冊它的邏輯（如果 `pywin32` 可用）。
        - **注意**：此處理程序現在**不直接**終止 MCP 伺服器進程（因為 `mcp_server_processes` 字典不再被填充）。它的主要作用是確保在 Windows 上的各種退出事件（如關閉控制台窗口）能觸發 Python 的正常關閉流程，進而執行 `finally` 塊中的 `shutdown()` 函數，最終調用 `exit_stack.aclose()` 來讓 `stdio_client` 清理其子進程。
        - `terminate_all_mcp_servers` 函數雖然保留，但因 `mcp_server_processes` 為空而不會執行實際的終止操作。
    - **移除冗餘終止調用**：從 `shutdown` 函數中移除了對 `terminate_all_mcp_servers` 的直接調用，因為終止邏輯現在由 `exit_stack.aclose()` 間接觸發。
- **依賴項**：Windows 上的控制台事件處理仍然依賴 `pywin32` 套件。如果未安裝，程式會打印警告，關閉時的可靠性可能略有降低（但 `stdio_client` 的正常清理機制應在多數情況下仍然有效）。
- **效果**：恢復了與 `mcp` 庫的兼容性，同時通過標準的上下文管理和輔助性的 Windows 事件處理，實現了在主程式退出時關閉 MCP 伺服器子進程的目標。

</final_file_content>

IMPORTANT: For any future changes to this file, use the final_file_content shown above as your reference. This content reflects the current state of the file, including any auto-formatting (e.g., if you used single quotes but the formatter converted them to double quotes). Always base your SEARCH/REPLACE operations on this final version to ensure accuracy.<environment_details>
# VSCode Visible Files
ui_interaction.py
ui_interaction.py
ClaudeCode.md

# VSCode Open Tabs
config_template.py
test/llm_debug_script.py
chroma_client.py
main.py
ClaudeCode.md
Setup.py
llm_interaction.py

# Recently Modified Files
These files have been modified since you last accessed them (file was just edited so you may need to re-read it before editing):
ClaudeCode.md

# Current Time
5/2/2025, 11:11:05 AM (Asia/Taipei, UTC+8:00)

# Context Window Usage
796,173 / 1,000K tokens used (80%)

# Current Mode
ACT MODE
</environment_details>

</file_content>

Now that you have the latest state of the file, try the operation again with fewer, more precise SEARCH blocks. For large files especially, it may be prudent to try to limit yourself to <5 SEARCH/REPLACE blocks at a time, then wait for the user to respond with the result of the operation before following up with another replace_in_file call to make additional edits.
(If you run into this error 3 times in a row, you may use the write_to_file tool as a fallback.)
</error><environment_details>
# VSCode Visible Files
ClaudeCode.md

# VSCode Open Tabs
config_template.py
test/llm_debug_script.py
llm_interaction.py
wolf_control.py
.gitignore
chroma_client.py
batch_memory_record.py
memory_manager.py
game_monitor.py
game_manager.py
Setup.py
main.py
ClaudeCode.md
reembedding tool.py
config.py
memory_backup.py
tools/chroma_view.py
ui_interaction.py
remote_config.json

# Current Time
5/13/2025, 3:31:34 AM (Asia/Taipei, UTC+8:00)

# Context Window Usage
429,724 / 1,048.576K tokens used (41%)

# Current Mode
ACT MODE
</environment_details>

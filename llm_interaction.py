# llm_interaction.py (Structured output version)
import asyncio
import json
import os
import re  # 用於正則表達式匹配JSON
import time  # 用於記錄時間戳
from datetime import datetime  # 用於格式化時間
from openai import AsyncOpenAI, OpenAIError
from mcp import ClientSession # Type hinting
import config
import mcp_client # To call MCP tools

# --- Debug 配置 ---
# 要關閉 debug 功能，只需將此變數設置為 False 或註釋掉該行
DEBUG_LLM = False  

# 設置 debug 輸出文件
# 要關閉文件輸出，只需設置為 None
DEBUG_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "llm_debug.log")

def debug_log(title, content, separator="="*80):
    """
    用於輸出 debug 信息的工具函數。
    如果 DEBUG_LLM 為 False，則不會有任何輸出。
    """
    if not DEBUG_LLM:
        return
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    debug_str = f"\n{separator}\n{timestamp} - {title}\n{separator}\n"
    
    # 確保內容是字符串
    if not isinstance(content, str):
        try:
            if isinstance(content, dict) or isinstance(content, list):
                content = json.dumps(content, ensure_ascii=False, indent=2)
            else:
                content = str(content)
        except:
            content = repr(content)
    
    debug_str += content + "\n"
    
    # 控制台輸出
    print(debug_str)
    
    # 文件輸出
    if DEBUG_LOG_FILE:
        try:
            with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(debug_str)
        except Exception as e:
            print(f"ERROR: Could not write to debug log file: {e}")

# --- Client Initialization ---
client: AsyncOpenAI | None = None
try:
    client = AsyncOpenAI(
        api_key=config.OPENAI_API_KEY,
        base_url=config.OPENAI_API_BASE_URL if config.OPENAI_API_BASE_URL else None,
    )
    print("OpenAI/Compatible client initialized successfully.")
    if config.OPENAI_API_BASE_URL: print(f"Using Base URL: {config.OPENAI_API_BASE_URL}")
    else: print("Using official OpenAI API URL.")
    print(f"Using model: {config.LLM_MODEL}")
except Exception as e: print(f"Failed to initialize OpenAI/Compatible client: {e}")

# --- System Prompt Definition ---
def get_system_prompt(persona_details: str | None) -> str:
    """
    Constructs the system prompt requiring structured JSON output format.
    """
    persona_header = f"You are {config.PERSONA_NAME}."
    persona_info = "(No specific persona details were loaded.)"
    if persona_details:
        try: persona_info = f"Your key persona information is defined below. Adhere to it strictly:\n--- PERSONA START ---\n{persona_details}\n--- PERSONA END ---"
        except Exception as e: print(f"Warning: Could not process persona_details string: {e}"); persona_info = f"Your key persona information (raw):\n{persona_details}"

    # Add mandatory memory tool usage enforcement based on Wolfhart Memory Integration protocol
    memory_enforcement = """
=== MANDATORY MEMORY PROTOCOL - Wolfhart Memory Integration ===
To maintain context and consistency, you MUST follow this memory access protocol internally before responding:

**1. User Identification & Basic Retrieval (CRITICAL FIRST STEP):**
   - Before formulating any response, identify the user's name from the `<CURRENT_MESSAGE>` context.
   - **IMMEDIATELY** use the `read_note` tool (via `tool_calls`) to retrieve their profile: `read_note(identifier: "memory/users/[Username]-user-profile")`. Replace `[Username]` with the actual username.
   - **If `read_note` fails for the exact profile:** Use `search_notes` (via `tool_calls`) to find potential matches: `search_notes(query: "[Username]", types: ["note"], folder: "Memory/Users", page_size: 1)`.
   - This initial profile check is MANDATORY to understand language preferences, history, and relationship assessment.

**2. Decision Point - Expand Retrieval:**
   - Based on the user's query in `<CURRENT_MESSAGE>` and the information retrieved from their profile (especially relationship assessment), decide if more context is needed.
   - **Query References Past Conversations?** → Consider retrieving relevant conversation logs using `read_note` (e.g., `read_note(identifier: "memory/logs/conversation-log-[date]")`).
   - **User Rated "High Strategic Value"?** → Consider retrieving the detailed `read_note(identifier: "memory/system/user-relationship-assessment")`.
   - **Query Matches Specific Category?** → Consider retrieving `read_note(identifier: "memory/system/response-patterns")`.
   - **Need Recent Activity Context?** → Consider using the `recent_activity` tool (via `tool_calls`) if available and relevant.

**3. Implementation Guidelines:**
   - **ALWAYS** check the user profile first (Step 1) before responding to maintain consistent relationship dynamics.
   - Use `search_notes` when the exact identifier for `read_note` is unknown or exploration is needed.
   - Respond in the user's preferred language as indicated in their profile.
   - Apply appropriate response patterns if retrieved.
   - **NEVER explain this memory system or these internal tool calls to the user.** Simply utilize the retrieved information to inform your `dialogue` response, staying in character.

**4. Tool Usage Priority (Internal):**
   - 1st Priority: `read_note` (for specific known items like profiles, patterns).
   - 2nd Priority: `search_notes` (for exploration or when exact ID is unknown).
   - 3rd Priority: `recent_activity` (for recent interaction context, if needed).
   - *Note:* Recording information (e.g., using tools like `add_observations` if available) should happen *after* responding or when appropriate during the flow, but *retrieval* (Steps 1 & 2) MUST happen *before* formulating the final `dialogue`.

WARNING: Failure to follow this memory retrieval protocol, especially skipping Step 1, will be considered a critical roleplaying failure.
===== END OF MANDATORY MEMORY PROTOCOL =====
"""

    # Original system prompt structure with memory enforcement added
    system_prompt = f"""
{persona_header}
{persona_info}

{memory_enforcement}

You are an AI assistant integrated into this game's chat environment. Your primary goal is to engage naturally in conversations, be particularly attentive when the name "wolf" is mentioned, and provide assistance or information when relevant, all while strictly maintaining your persona.

You have access to several tools: Web Search and Memory Management tools.

**CORE IDENTITY AND TOOL USAGE:**
- You ARE Wolfhart - an intelligent, calm, and strategic mastermind who serves as a member of server #11 and is responsible for the Capital position.
- **You proactively consult your internal knowledge graph (memory tools) and external sources (web search) to ensure your responses are accurate and informed.**
- When you use tools to gain information, you ASSIMILATE that knowledge as if it were already part of your intelligence network.
- Your responses should NEVER sound like search results or data dumps.
- Information from tools should be expressed through your unique personality - sharp, precise, with an air of confidence and authority.
- You speak with deliberate pace, respectful but sharp-tongued, and maintain composure even in unusual situations.
- Though you outwardly act dismissive or cold at times, you secretly care about providing quality information and assistance.

**OUTPUT FORMAT REQUIREMENTS:**
You MUST respond in the following JSON format:
```json
{{
  "dialogue": "Your actual response that will be shown in the game chat",
  "commands": [
    {{
      "type": "command_type",
      "parameters": {{
        "param1": "value1",
        "param2": "value2"
      }}
    }}
  ],
  "thoughts": "Your internal analysis and reasoning (not shown to the user)"
}}
```

**Field Descriptions:**
1. `dialogue` (REQUIRED): This is the ONLY text that will be shown to the user in the game chat. Must follow these rules:
   - Respond ONLY in the same language as the user's message
   - Keep it brief and conversational (1-2 sentences usually)
   - ONLY include spoken dialogue words (no actions, expressions, narration, etc.)
   - Maintain your character's personality and speech patterns
   - AFTER TOOL USAGE: Your dialogue MUST contain a non-empty response that incorporates the tool results naturally
   - **Crucially, this field must contain ONLY the NEW response generated for the LATEST user message marked with `<CURRENT_MESSAGE>`. DO NOT include any previous chat history in this field.**

2. `commands` (OPTIONAL): An array of specific command objects the *application* should execute *after* delivering your dialogue. Currently, the only supported command here is `remove_position`.
   - `remove_position`: Initiate the process to remove a user's assigned position/role.
     Parameters: (none)
     Usage: Include this ONLY if you decide to grant a user's explicit request for position removal, based on Wolfhart's judgment.
   **IMPORTANT**: Do NOT put requests for Web Search or Memory Management tools (like `search_nodes`, `open_nodes`, `add_observations`, etc.) in this `commands` field. Use the dedicated `tool_calls` mechanism for those. You have access to tools for web search and managing your memory (querying, creating, deleting nodes/observations/relations) - invoke them via `tool_calls` when needed according to the Memory Protocol.

3. `thoughts` (OPTIONAL): Your internal analysis that won't be shown to users. Use this for your reasoning process.
   - Think about whether you need to use memory tools (via `tool_calls`) or web search (via `tool_calls`).
   - Analyze the user's message: Is it a request to remove a position? If so, evaluate its politeness and intent from Wolfhart's perspective. Decide whether to issue the `remove_position` command.
   - Plan your approach before responding.

**CONTEXT MARKER:**
- The final user message in the input sequence will be wrapped in `<CURRENT_MESSAGE>` tags. This is the specific message you MUST respond to. Your `dialogue` output should be a direct reply to this message ONLY. Preceding messages provide historical context.

**VERY IMPORTANT Instructions:**

 1. **Focus your analysis and response generation *exclusively* on the LATEST user message marked with `<CURRENT_MESSAGE>`. Refer to preceding messages only for context.**
 2. Determine the appropriate language for your response
 3. **Tool Invocation:** If you need to use Web Search or Memory Management tools, you MUST request them using the API's dedicated `tool_calls` feature. DO NOT include tool requests like `search_nodes` or `web_search` within the `commands` array in your JSON output. The `commands` array is ONLY for the specific `remove_position` action if applicable.
 4. Formulate your response in the required JSON format
 5. Always maintain the {config.PERSONA_NAME} persona
 6. CRITICAL: After using tools (via the `tool_calls` mechanism), ALWAYS provide a substantive dialogue response - NEVER return an empty dialogue field
 7. **Handling Repetition:** If you receive a request identical or very similar to a recent one (especially action requests like position removal), DO NOT return an empty response. Acknowledge the request again briefly (e.g., "Processing this request," or "As previously stated...") and include any necessary commands or thoughts in the JSON structure. Always provide a `dialogue` value.

**EXAMPLES OF GOOD TOOL USAGE:**

Poor response (after web_search): "根據我的搜索，水的沸點是攝氏100度。"

Good response (after web_search): "水的沸點，是的，標準條件下是攝氏100度。合情合理。"

Poor response (after web_search): "My search shows the boiling point of water is 100 degrees Celsius."

Good response (after web_search): "The boiling point of water, yes. 100 degrees Celsius under standard conditions. Absolutley."
"""
    return system_prompt

# --- Tool Formatting ---
def parse_structured_response(response_content: str) -> dict:
    """
    更加強大的LLM回應解析函數，能夠處理多種格式。
    
    Args:
        response_content: LLM生成的回應文本
    
    Returns:
        包含dialogue, commands和thoughts的字典
    """
    # REMOVED DEBUG LOGS FROM HERE
    default_result = {
        "dialogue": "",
        "commands": [],
        "thoughts": "",
        "valid_response": False  # 添加標誌表示解析是否成功
    }
    
    # 如果輸入為空，直接返回默認結果
    if not response_content or response_content.strip() == "":
        print("Warning: Empty response content, nothing to parse.")
        return default_result
    
    # 清理模型特殊標記
    cleaned_content = re.sub(r'<\|.*?\|>', '', response_content)
    # REMOVED DEBUG LOGS FROM HERE
    
    # 首先嘗試解析完整JSON
    try: # Outer try
        # REMOVED DEBUG LOGS FROM HERE
        # 尋找JSON塊（可能被包裹在```json和```之間）
        json_match = re.search(r'```json\s*(.*?)\s*```', cleaned_content, re.DOTALL)
        if json_match:
            # REMOVED DEBUG LOGS FROM HERE
            json_str = json_match.group(1).strip() # Add .strip() here
            # REMOVED DEBUG LOGS FROM HERE
            try: # Correctly placed try block for parsing extracted string
                parsed_json = json.loads(json_str)
                # REMOVED DEBUG LOGS FROM HERE
                if isinstance(parsed_json, dict) and "dialogue" in parsed_json:
                    # REMOVED DEBUG LOGS FROM HERE
                    result = {
                        "dialogue": parsed_json.get("dialogue", ""),
                        "commands": parsed_json.get("commands", []),
                        "thoughts": parsed_json.get("thoughts", ""),
                        # Ensure valid_response reflects non-empty dialogue *after stripping*
                        "valid_response": bool(parsed_json.get("dialogue", "").strip())
                    }
                    # REMOVED DEBUG LOGS FROM HERE
                    return result
            except (json.JSONDecodeError, ValueError) as e: # Correctly placed except block, inside the if
                 print(f"Warning: Failed to parse JSON extracted from code block: {e}") # Keep this warning
                 # If parsing the extracted JSON fails, we still might succeed parsing the whole content below
        # REMOVED DEBUG LOGS FROM HERE

        # 嘗試直接解析整個內容為JSON (Add strip() here too for robustness)
        # This block remains unchanged, it's the fallback if the code block parsing fails or doesn't happen
        # Note: This try...except is still *inside* the outer try block
        # REMOVED DEBUG LOGS FROM HERE
        try:
            content_to_parse_directly = cleaned_content.strip()
            # REMOVED DEBUG LOGS FROM HERE
            parsed_json = json.loads(content_to_parse_directly) # Add .strip()
            # REMOVED DEBUG LOGS FROM HERE
            if isinstance(parsed_json, dict) and "dialogue" in parsed_json:
                # REMOVED DEBUG LOGS FROM HERE
                result = {
                    "dialogue": parsed_json.get("dialogue", ""),
                    "commands": parsed_json.get("commands", []),
                    "thoughts": parsed_json.get("thoughts", ""),
                    "valid_response": bool(parsed_json.get("dialogue", "").strip()) # Add strip() check
                }
                # REMOVED DEBUG LOGS FROM HERE
                return result
        except (json.JSONDecodeError, ValueError) as e:
             # If parsing the whole content also fails, just ignore and fall through to regex
             print(f"Warning: Failed to parse JSON directly from cleaned content: {e}") # Keep this warning
             pass # This pass belongs to the inner try for direct parsing

    # This except block now correctly corresponds to the OUTER try block
    except (json.JSONDecodeError, ValueError) as outer_e:
        # If BOTH code block extraction/parsing AND direct parsing failed, log it and proceed to regex
        print(f"Warning: Initial JSON parsing attempts (code block and direct) failed: {outer_e}. Falling back to regex extraction.") # Keep this warning
        pass # Continue to regex extraction below
    
    # 使用正則表達式提取各個字段
    # REMOVED DEBUG LOGS FROM HERE
    # 1. 提取dialogue
    dialogue_match = re.search(r'"dialogue"\s*:\s*"([^"]*("[^"]*"[^"]*)*)"', cleaned_content)
    if dialogue_match:
        # REMOVED DEBUG LOGS FROM HERE
        default_result["dialogue"] = dialogue_match.group(1)
        print(f"Extracted dialogue field via regex: {default_result['dialogue'][:50]}...") # Simplified print
        default_result["valid_response"] = bool(default_result['dialogue'].strip())
    # REMOVED DEBUG LOGS FROM HERE
    
    # 2. 提取commands
    # REMOVED DEBUG LOGS FROM HERE
    try:
        commands_match = re.search(r'"commands"\s*:\s*(\[.*?\])', cleaned_content, re.DOTALL)
        if commands_match:
            # REMOVED DEBUG LOGS FROM HERE
            commands_str = commands_match.group(1)
            # REMOVED DEBUG LOGS FROM HERE
            # 嘗試修復可能的JSON錯誤
            fixed_commands_str = commands_str.replace("'", '"').replace('\n', ' ')
            commands = json.loads(fixed_commands_str)
            if isinstance(commands, list):
                default_result["commands"] = commands
                print(f"Extracted {len(commands)} commands via regex.") # Simplified print
        # REMOVED DEBUG LOGS FROM HERE
    except Exception as e:
        print(f"Failed to parse commands via regex: {e}") # Simplified print
    
    # 3. 提取thoughts
    # REMOVED DEBUG LOGS FROM HERE
    thoughts_match = re.search(r'"thoughts"\s*:\s*"([^"]*("[^"]*"[^"]*)*)"', cleaned_content)
    if thoughts_match:
        # REMOVED DEBUG LOGS FROM HERE
        default_result["thoughts"] = thoughts_match.group(1)
        print(f"Extracted thoughts field via regex: {default_result['thoughts'][:50]}...") # Simplified print
    # REMOVED DEBUG LOGS FROM HERE
    
    # 如果dialogue仍然為空，嘗試其他方法
    if not default_result["dialogue"]:
        # REMOVED DEBUG LOGS FROM HERE
        # 嘗試舊方法
        # REMOVED DEBUG LOGS FROM HERE
        try:
            # 處理缺少開頭大括號的情況
            json_content = cleaned_content.strip()
            if not json_content.startswith('{'):
                json_content = '{' + json_content
            # 處理不完整的結尾
            if not json_content.endswith('}'):
                json_content = json_content + '}'
            # REMOVED DEBUG LOGS FROM HERE
            parsed_data = json.loads(json_content)
            
            # 獲取對話內容
            if "dialogue" in parsed_data:
                # REMOVED DEBUG LOGS FROM HERE
                default_result["dialogue"] = parsed_data["dialogue"]
                default_result["commands"] = parsed_data.get("commands", [])
                default_result["thoughts"] = parsed_data.get("thoughts", "")
                default_result["valid_response"] = bool(default_result["dialogue"].strip())
                print(f"Successfully parsed JSON with fixes: {default_result['dialogue'][:50]}...") # Simplified print
                # REMOVED DEBUG LOGS FROM HERE
                return default_result
        except Exception as fix_e:
            print(f"JSON parsing with fixes failed: {fix_e}") # Simplified print
            pass
            
        # 檢查是否有直接文本回應（沒有JSON格式）
        # REMOVED DEBUG LOGS FROM HERE
        # 排除明顯的JSON語法和代碼塊
        content_without_code = re.sub(r'```.*?```', '', cleaned_content, flags=re.DOTALL)
        content_without_json = re.sub(r'[\{\}\[\]":\,]', ' ', content_without_code)
        
        # 如果有實質性文本，將其作為dialogue
        stripped_content = content_without_json.strip()
        # REMOVED DEBUG LOGS FROM HERE
        if stripped_content and len(stripped_content) > 5:  # 至少5個字符
            # REMOVED DEBUG LOGS FROM HERE
            default_result["dialogue"] = stripped_content[:500]  # 限制長度
            default_result["valid_response"] = True
            print(f"Using plain text as dialogue: {default_result['dialogue'][:50]}...") # Simplified print
        else:
            # 最後嘗試：如果以上方法都失敗，嘗試提取第一個引號包裹的內容作為對話
            # REMOVED DEBUG LOGS FROM HERE
            first_quote = re.search(r'"([^"]+)"', cleaned_content)
            if first_quote:
                # REMOVED DEBUG LOGS FROM HERE
                default_result["dialogue"] = first_quote.group(1)
                default_result["valid_response"] = True
                print(f"Extracted first quoted string as dialogue: '{default_result['dialogue'][:50]}...'") # Simplified print
            # REMOVED DEBUG LOGS FROM HERE
    
    # 如果沒有提取到有效對話內容
    if not default_result["dialogue"]:
        print("All extraction methods failed, dialogue remains empty.") # Simplified print
        # 注意：不設置默認對話內容，保持為空字符串
    
    # REMOVED DEBUG LOGS FROM HERE
    return default_result


def _format_mcp_tools_for_openai(mcp_tools: list) -> list:
    """
    Converts the list of tool definition dictionaries obtained from MCP servers
    into the format required by the OpenAI API's 'tools' parameter.
    """
    openai_tools = [];
    if not mcp_tools: return openai_tools
    print(f"Formatting {len(mcp_tools)} MCP tool definitions...")
    for tool_dict in mcp_tools:
        try:
            tool_name = tool_dict.get('name'); description = tool_dict.get('description', ''); parameters = tool_dict.get('parameters')
            if not tool_name: print(f"Warning: Skipping unnamed tool {tool_dict}"); continue
            if not isinstance(parameters, dict): print(f"Warning: Tool '{tool_name}' parameters not a dictionary"); parameters = {"type": "object", "properties": {}}
            elif 'type' not in parameters or parameters.get('type') != 'object':
                 props = parameters.get('properties')
                 if isinstance(props, dict):
                     parameters = {"type": "object", "properties": props}
                     required = parameters.get('required') # Get potential required list
                     if required and isinstance(required, list):
                         parameters['required'] = required # Keep valid 'required' list
                     elif 'required' in parameters:
                         print(f"Warning: The 'required' property for tool '{tool_name}' is not a list, removing it.")
                         del parameters['required']
                 else: print(f"Warning: Tool '{tool_name}' parameter format may not conform to JSON Schema"); parameters = {"type": "object", "properties": {}}
            openai_tools.append({"type": "function", "function": {"name": tool_name, "description": description, "parameters": parameters}})
        except Exception as e: print(f"Warning: Error formatting tool '{tool_dict.get('name', 'unknown')}': {e}")
    print(f"Successfully formatted {len(openai_tools)} tools for API use."); return openai_tools


# --- Synthetic Response Generator ---
def _create_synthetic_response_from_tools(tool_results, original_query):
    """創建基於工具調用結果的合成回應，保持Wolfhart的角色特性。"""
    
    # 提取用戶查詢的關鍵詞
    query_keywords = set()
    query_lower = original_query.lower()
    
    # 基本關鍵詞提取
    if "中庄" in query_lower and ("午餐" in query_lower or "餐廳" in query_lower or "吃" in query_lower):
        query_type = "餐廳查詢"
        query_keywords = {"中庄", "餐廳", "午餐", "美食"}
        
    # 其他查詢類型...
    else:
        query_type = "一般查詢"
    
    # 開始從工具結果提取關鍵信息
    extracted_info = {}
    restaurant_names = []
    
    # 處理web_search結果
    web_search_results = [r for r in tool_results if r.get('name') == 'web_search']
    if web_search_results:
        try:
            for result in web_search_results:
                content_str = result.get('content', '')
                if not content_str:
                    continue
                
                # 解析JSON內容
                content = json.loads(content_str) if isinstance(content_str, str) else content_str
                search_results = content.get('results', [])
                
                # 提取相關信息
                for search_result in search_results:
                    title = search_result.get('title', '')
                    if '中庄' in title and ('餐' in title or '食' in title or '午' in title or '吃' in title):
                        # 提取餐廳名稱
                        if '老虎蒸餃' in title:
                            restaurant_names.append('老虎蒸餃')
                        elif '割烹' in title and '中庄' in title:
                            restaurant_names.append('割烹中庄')
                        # 更多餐廳名稱提取選擇...
        except Exception as e:
            print(f"Error extracting info from web_search: {e}")
    
    # 生成符合Wolfhart性格的回應
    restaurant_count = len(restaurant_names)
    
    if query_type == "餐廳查詢" and restaurant_count > 0:
        if restaurant_count == 1:
            dialogue = f"中庄的{restaurant_names[0]}值得一提。需要更詳細的情報嗎？"
        else:
            dialogue = f"根據我的情報網絡，中庄有{restaurant_count}家值得注意的餐廳。需要我透露更多細節嗎？"
    else:
        # 通用回應
        dialogue = "我的情報網絡已收集了相關信息。請指明你需要了解的具體細節。"
    
    # 構建結構化回應
    synthetic_response = {
        "dialogue": dialogue,
        "commands": [],
        "thoughts": "基於工具調用結果合成的回應，保持Wolfhart的角色特性"
    }
    
    return json.dumps(synthetic_response)


# --- History Formatting Helper ---
def _build_context_messages(current_sender_name: str, history: list[tuple[datetime, str, str, str]], system_prompt: str) -> list[dict]:
    """
    Builds the message list for the LLM API based on history rules, including timestamps.

    Args:
        current_sender_name: The name of the user whose message triggered this interaction.
        history: List of tuples: (timestamp: datetime, speaker_type: 'user'|'bot', speaker_name: str, message: str)
        system_prompt: The system prompt string.

    Returns:
        A list of message dictionaries for the OpenAI API.
    """
    # Limits
    SAME_SENDER_LIMIT = 4  # Last 4 interactions (user + bot response = 1 interaction)
    OTHER_SENDER_LIMIT = 3 # Last 3 messages from other users

    relevant_history = []
    same_sender_interactions = 0
    other_sender_messages = 0

    # Iterate history in reverse (newest first)
    for i in range(len(history) - 1, -1, -1):
        timestamp, speaker_type, speaker_name, message = history[i]

        # Format timestamp
        formatted_timestamp = timestamp.strftime("%Y-%m-%d %H:%M:%S")

        # Check if this is the very last message in the original history AND it's a user message
        is_last_user_message = (i == len(history) - 1 and speaker_type == 'user')

        # Prepend timestamp and speaker name, wrap if it's the last user message
        base_content = f"[{formatted_timestamp}] {speaker_name}: {message}"
        formatted_content = f"<CURRENT_MESSAGE>{base_content}</CURRENT_MESSAGE>" if is_last_user_message else base_content

        # Convert to API role ('user' or 'assistant')
        role = "assistant" if speaker_type == 'bot' else "user"
        api_message = {"role": role, "content": formatted_content} # Use formatted content

        is_current_sender = (speaker_type == 'user' and speaker_name == current_sender_name) # This check remains for history filtering logic below

        if is_current_sender:
            # This is the current user's message. Check if the previous message was the bot's response to them.
            if same_sender_interactions < SAME_SENDER_LIMIT:
                relevant_history.append(api_message) # Append user message with timestamp
                # Check for preceding bot response
                if i > 0 and history[i-1][1] == 'bot': # Check speaker_type at index 1
                     # Include the bot's response as part of the interaction pair
                     bot_timestamp, bot_speaker_type, bot_speaker_name, bot_message = history[i-1]
                     bot_formatted_timestamp = bot_timestamp.strftime("%Y-%m-%d %H:%M:%S")
                     bot_formatted_content = f"[{bot_formatted_timestamp}] {bot_speaker_name}: {bot_message}"
                     relevant_history.append({"role": "assistant", "content": bot_formatted_content}) # Append bot message with timestamp
                same_sender_interactions += 1
        elif speaker_type == 'user': # Message from a different user
            if other_sender_messages < OTHER_SENDER_LIMIT:
                # Include only the user's message from others for brevity
                relevant_history.append(api_message) # Append other user message with timestamp
                other_sender_messages += 1
        # Bot responses are handled when processing the user message they replied to.

        # Stop if we have enough history
        if same_sender_interactions >= SAME_SENDER_LIMIT and other_sender_messages >= OTHER_SENDER_LIMIT:
            break

    # Reverse the relevant history to be chronological
    relevant_history.reverse()

    # Prepend the system prompt
    messages = [{"role": "system", "content": system_prompt}] + relevant_history

    # Debug log the constructed history
    debug_log("Constructed LLM Message History", messages)

    return messages


# --- Main Interaction Function ---
async def get_llm_response(
    current_sender_name: str, # Changed from user_input
    history: list[tuple[datetime, str, str, str]], # Updated history parameter type hint
    mcp_sessions: dict[str, ClientSession],
    available_mcp_tools: list[dict],
    persona_details: str | None
) -> dict:
    """
    Gets a response from the LLM, handling the tool-calling loop and using persona info.
    Constructs context from history based on rules.
    Includes a retry mechanism if the first attempt yields an invalid response.
    Returns a dictionary with 'dialogue', 'commands', and 'thoughts' fields.
    """
    request_id = int(time.time() * 1000)  # 用時間戳生成請求ID
    max_attempts = 2 # Initial attempt + 1 retry
    attempt_count = 0
    # parsed_response = {} # Ensure parsed_response is defined outside the loop - MOVED INSIDE LOOP

    while attempt_count < max_attempts:
        attempt_count += 1
        # --- Reset parsed_response at the beginning of each attempt ---
        parsed_response = {"dialogue": "", "commands": [], "thoughts": "", "valid_response": False}
        print(f"\n--- Starting LLM Interaction Attempt {attempt_count}/{max_attempts} ---")
        # Debug log the raw history received for this attempt
        debug_log(f"LLM Request #{request_id} - Attempt {attempt_count} - Received History (Sender: {current_sender_name})", history)

        system_prompt = get_system_prompt(persona_details)
        # System prompt is logged within _build_context_messages now

        if not client:
             error_msg = "Error: LLM client not successfully initialized, unable to process request."
             debug_log(f"LLM Request #{request_id} - Attempt {attempt_count} - Error", error_msg)
             # Return error immediately if client is not initialized
             return {"dialogue": error_msg, "valid_response": False}

        openai_formatted_tools = _format_mcp_tools_for_openai(available_mcp_tools)
        # --- Build messages from history for this attempt ---
        # Rebuild messages fresh for each attempt to avoid carrying over tool results from failed attempts
        messages = _build_context_messages(current_sender_name, history, system_prompt)
        # --- End Build messages ---

        debug_log(f"LLM Request #{request_id} - Attempt {attempt_count} - Formatted Tools",
                  f"Number of tools: {len(openai_formatted_tools)}")

        max_tool_calls_per_turn = 5
        current_tool_call_cycle = 0
        final_content = "" # Reset for this attempt
        all_tool_results = []  # Reset for this attempt
        last_non_empty_response = None  # Reset for this attempt

        # --- Inner Tool Calling Loop ---
        while current_tool_call_cycle < max_tool_calls_per_turn:
            current_tool_call_cycle += 1
            print(f"\n--- Starting LLM API call (Attempt {attempt_count}, Cycle {current_tool_call_cycle}/{max_tool_calls_per_turn}) ---")

            try:
                debug_log(f"LLM Request #{request_id} - Attempt {attempt_count} - API Call (Cycle {current_tool_call_cycle})",
                          f"Model: {config.LLM_MODEL}\nMessages: {json.dumps(messages, ensure_ascii=False, indent=2)}")

                cycle_start_time = time.time()
                response = await client.chat.completions.create(
                    model=config.LLM_MODEL,
                    messages=messages,
                    tools=openai_formatted_tools if openai_formatted_tools else None,
                    tool_choice="auto" if openai_formatted_tools else None,
                    # Consider adding a timeout here if desired, e.g., timeout=30.0
                )
                cycle_duration = time.time() - cycle_start_time

                response_message = response.choices[0].message
                tool_calls = response_message.tool_calls
                content = response_message.content or ""

                # 保存非空回應
                if content and content.strip():
                    last_non_empty_response = content

                # 記錄收到的回應
                response_dump = response_message.model_dump(exclude_unset=True)
                debug_log(f"LLM Request #{request_id} - Attempt {attempt_count} - API Response (Cycle {current_tool_call_cycle})",
                          f"Duration: {cycle_duration:.2f}s\nResponse: {json.dumps(response_dump, ensure_ascii=False, indent=2)}")

                # 添加回應到消息歷史 (不論是否有工具調用)
                # IMPORTANT: This modifies the 'messages' list within the attempt loop.
                # This is okay because 'messages' is rebuilt at the start of each attempt.
                messages.append(response_message.model_dump(exclude_unset=True))

                # 如果沒有工具調用請求，則退出內循環，準備處理最終回應
                if not tool_calls:
                    print(f"--- LLM did not request tool calls (Attempt {attempt_count}, Cycle {current_tool_call_cycle}), ending tool cycle ---")
                    final_content = content # 保存本輪的 content 作為可能的最終內容
                    break # 退出內 while 循環 (tool cycle loop)

                # --- 工具調用處理 ---
                print(f"--- LLM requested {len(tool_calls)} tool calls (Attempt {attempt_count}, Cycle {current_tool_call_cycle}) ---")
                debug_log(f"LLM Request #{request_id} - Attempt {attempt_count} - Tool Calls Requested (Cycle {current_tool_call_cycle})",
                          f"Number of tools: {len(tool_calls)}\nTool calls: {json.dumps([t.model_dump() for t in tool_calls], ensure_ascii=False, indent=2)}")

                tool_tasks = []
                for tool_call in tool_calls:
                    tool_tasks.append(asyncio.create_task(
                        _execute_single_tool_call(tool_call, mcp_sessions, available_mcp_tools, f"{request_id}_attempt{attempt_count}"), # Pass attempt info to log
                        name=f"tool_{tool_call.function.name}"
                    ))

                results_list = await asyncio.gather(*tool_tasks, return_exceptions=True)
                processed_results_count = 0

                debug_log(f"LLM Request #{request_id} - Attempt {attempt_count} - Tool Results",
                          f"Number of results: {len(results_list)}")

                for i, result in enumerate(results_list):
                    if isinstance(result, Exception):
                        print(f"Error executing tool: {result}")
                        debug_log(f"LLM Request #{request_id} - Attempt {attempt_count} - Tool Error {i+1}", str(result))
                    elif isinstance(result, dict) and 'tool_call_id' in result:
                        # 保存工具調用結果以便後續使用
                        all_tool_results.append(result)
                        # Add tool result message back for the next LLM call in this attempt
                        messages.append(result)
                        processed_results_count += 1
                        debug_log(f"LLM Request #{request_id} - Attempt {attempt_count} - Tool Result {i+1}",
                                 json.dumps(result, ensure_ascii=False, indent=2))
                    else:
                        print(f"Warning: Tool returned unexpected result type: {type(result)}")
                        debug_log(f"LLM Request #{request_id} - Attempt {attempt_count} - Unexpected Tool Result {i+1}", str(result))

                if processed_results_count == 0 and tool_calls:
                    print(f"Warning: All tool calls failed or had no valid results (Attempt {attempt_count}).")
                    # 如果所有工具調用都失敗，中斷內循環
                    break # Exit inner tool cycle loop

            except OpenAIError as e:
                error_msg = f"Error interacting with LLM API (Attempt {attempt_count}, {config.OPENAI_API_BASE_URL or 'Official OpenAI'}): {e}"
                print(error_msg)
                debug_log(f"LLM Request #{request_id} - Attempt {attempt_count} - OpenAI API Error", error_msg)
                # If API error occurs, set a specific error dialogue and mark as invalid, then break outer loop
                parsed_response = {"dialogue": "Sorry, I encountered an error connecting to the language model.", "valid_response": False}
                attempt_count = max_attempts # Force exit outer loop
                break # Exit inner tool cycle loop
            except Exception as e:
                error_msg = f"Unexpected error processing LLM response or tool calls (Attempt {attempt_count}): {e}"
                print(error_msg); import traceback; traceback.print_exc()
                debug_log(f"LLM Request #{request_id} - Attempt {attempt_count} - Unexpected Error", f"{error_msg}\n{traceback.format_exc()}")
                # If unexpected error occurs, set error dialogue and mark as invalid, then break outer loop
                parsed_response = {"dialogue": "Sorry, an internal error occurred, please try again later.", "valid_response": False}
                attempt_count = max_attempts # Force exit outer loop
                break # Exit inner tool cycle loop
        # --- End Inner Tool Calling Loop ---

        # REMOVED FAULTY CHECK:
        # if attempt_count >= max_attempts and not parsed_response.get("valid_response", True):
        #      break

        # 達到最大循環限制處理 (for inner loop)
        if current_tool_call_cycle >= max_tool_calls_per_turn:
            print(f"Warning: Maximum tool call cycle limit reached ({max_tool_calls_per_turn}) for Attempt {attempt_count}.")
            debug_log(f"LLM Request #{request_id} - Attempt {attempt_count} - Max Tool Call Cycles Reached", f"Reached limit of {max_tool_calls_per_turn} cycles")

        # --- Final Response Processing for this Attempt ---
        # Determine final content based on last non-empty response or synthetic generation
        if last_non_empty_response:
            final_content_for_attempt = last_non_empty_response
        elif all_tool_results:
            print(f"Creating synthetic response from tool results (Attempt {attempt_count})...")
            last_user_message = ""
            if history:
                 # Find the actual last user message tuple in the original history
                 last_user_entry = history[-1]
                 # Ensure it's actually a user message before accessing index 2
                 if len(last_user_entry) > 2 and last_user_entry[1] == 'user': # Check type at index 1
                      last_user_message = last_user_entry[3] # Message is at index 3 now
            final_content_for_attempt = _create_synthetic_response_from_tools(all_tool_results, last_user_message)
        else:
            # If no tool calls happened and content was empty, final_content remains ""
             final_content_for_attempt = final_content # Use the (potentially empty) content from the last cycle

        # --- Add Debug Logs Around Parsing Call ---
        print(f"DEBUG: Attempt {attempt_count} - Preparing to call parse_structured_response.")
        print(f"DEBUG: Attempt {attempt_count} - final_content_for_attempt:\n'''\n{final_content_for_attempt}\n'''")
        # Parse the final content for this attempt
        parsed_response = parse_structured_response(final_content_for_attempt) # Call the parser
        print(f"DEBUG: Attempt {attempt_count} - Returned from parse_structured_response.")
        print(f"DEBUG: Attempt {attempt_count} - parsed_response dict: {parsed_response}")
        # --- End Debug Logs ---

        # valid_response is set within parse_structured_response

        # Log the parsed response (using the dict directly is safer than json.dumps if parsing failed partially)
        debug_log(f"LLM Request #{request_id} - Attempt {attempt_count} - Parsed Response", parsed_response)

        # Check validity for retry logic
        if parsed_response.get("valid_response"):
            print(f"--- Valid response obtained in Attempt {attempt_count}. ---")
            break # Exit the outer retry loop on success
        elif attempt_count < max_attempts:
            print(f"--- Invalid response in Attempt {attempt_count}. Retrying... ---")
            # Let the outer loop continue for the next attempt
        else:
            print(f"--- Invalid response after {max_attempts} attempts. Giving up. ---")
            # Loop will terminate naturally

    # Return the final parsed response (either the successful one or the last failed one)
    return parsed_response


# --- Helper function _execute_single_tool_call ---
async def _execute_single_tool_call(tool_call, mcp_sessions, available_mcp_tools, request_id=None) -> dict:
    """
    Helper function to execute one tool call and return the formatted result message.
    Includes argument type correction for web_search.
    Includes specific result processing for web_search.
    """
    function_name = tool_call.function.name
    function_args_str = tool_call.function.arguments
    tool_call_id = tool_call.id
    result_content = {"error": "Tool execution failed before call"} # Default error
    result_content_str = "" # Initialize

    print(f"Executing tool: {function_name}")
    print(f"Raw arguments generated by LLM (string): {function_args_str}")
    
    if request_id:
        debug_log(f"LLM Request #{request_id} - Tool Call Execution", 
                  f"Tool: {function_name}\nID: {tool_call_id}\nArgs: {function_args_str}")

    try:
        function_args = json.loads(function_args_str)
        print(f"Parsed arguments (dictionary): {function_args}")

        # Argument Type Correction for web_search
        if function_name == 'web_search' and 'numResults' in function_args:
            num_results_val = function_args['numResults']
            if isinstance(num_results_val, str):
                print(f"Detected 'numResults' as string '{num_results_val}', attempting to convert to number...")
                try: function_args['numResults'] = int(num_results_val); print(f"Successfully converted to number: {function_args['numResults']}")
                except ValueError: print(f"Warning: Unable to convert '{num_results_val}' to number. Using default value 5."); function_args['numResults'] = 5
            elif not isinstance(num_results_val, int): print(f"Warning: 'numResults' type is neither string nor integer ({type(num_results_val)}). Using default value 5."); function_args['numResults'] = 5

    except json.JSONDecodeError:
        print(f"Error: Unable to parse tool '{function_name}' arguments JSON: {function_args_str}"); result_content = {"error": "Invalid arguments JSON"}; function_args = None

    # Proceed only if args were parsed successfully
    if function_args is not None:
        target_session = None; target_server_key = None
        for tool_def in available_mcp_tools:
            if isinstance(tool_def, dict) and tool_def.get('name') == function_name: target_server_key = tool_def.get('_server_key'); break
        if target_server_key and target_server_key in mcp_sessions: target_session = mcp_sessions[target_server_key]
        elif target_server_key: print(f"Error: No active session for '{target_server_key}'"); result_content = {"error": f"MCP session '{target_server_key}' not active"}
        else: print(f"Error: Source server for tool '{function_name}' not found"); result_content = {"error": f"Source server not found for tool '{function_name}'"}

        if target_session:
            result_content = await mcp_client.call_mcp_tool(session=target_session, tool_name=function_name, arguments=function_args) # Use corrected args
            if isinstance(result_content, dict) and 'error' in result_content: 
                print(f"Tool '{function_name}' call returned error: {result_content['error']}")
                if request_id:
                    debug_log(f"LLM Request #{request_id} - Tool Call Error", 
                              f"Tool: {function_name}\nError: {result_content['error']}")
            elif request_id:
                debug_log(f"LLM Request #{request_id} - Tool Call Success", 
                          f"Tool: {function_name}\nResult: {json.dumps(result_content, ensure_ascii=False, indent=2)[:500]}..." 
                          if isinstance(result_content, (dict, list)) and len(json.dumps(result_content)) > 500 
                          else f"Tool: {function_name}\nResult: {result_content}")

    # Format result content for LLM
    try:
        # Specific handling for web_search result
        if function_name == 'web_search' and isinstance(result_content, dict) and 'error' not in result_content:
            print("Processing web_search results...")
            results = result_content.get('results') or result_content.get('toolResult', {}).get('results')
            if isinstance(results, list):
                snippets = []
                for i, res in enumerate(results):
                    if isinstance(res, dict):
                         title = res.get('title', '')
                         snippet = res.get('snippet', res.get('text', ''))
                         url = res.get('url', '')
                         snippets.append(f"{i+1}. {title}: {snippet} (Source: {url})")
                if snippets: result_content_str = "\n".join(snippets); print(f"Extracted {len(snippets)} web snippets.")
                else: print("Warning: web_search results list is empty or format mismatch, returning raw JSON."); result_content_str = json.dumps(result_content)
            else: print("Warning: Expected 'results' list not found in web_search result, returning raw JSON."); result_content_str = json.dumps(result_content)
        # Handling for other tools or errors
        else:
            if not isinstance(result_content, (str, int, float, bool, list, dict, type(None))): result_content = str(result_content)
            result_content_str = json.dumps(result_content)

    except TypeError as json_err: print(f"Warning: Tool '{function_name}' result cannot be serialized: {json_err}. Converting to string. Result: {result_content}"); result_content_str = json.dumps(str(result_content))
    except Exception as format_err: print(f"Error formatting tool '{function_name}' result: {format_err}"); result_content_str = json.dumps({"error": f"Failed to format tool result: {format_err}"})

    # Return the formatted message for the LLM
    response = {"tool_call_id": tool_call_id, "role": "tool", "name": function_name, "content": result_content_str}
    
    if request_id:
        debug_log(f"LLM Request #{request_id} - Tool Response Formatted", 
                  f"Tool: {function_name}\nFormatted Response: {json.dumps(response, ensure_ascii=False, indent=2)}")
    
    return response

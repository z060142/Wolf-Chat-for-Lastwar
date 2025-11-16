# llm_interaction.py (Structured output version)
import asyncio
import json
import os
import random # Added for synthetic response generation
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
def get_system_prompt(
    persona_details: str | None,
    user_profile: str | None = None,
    related_memories: list | None = None,
    bot_knowledge: list | None = None,
    active_mcp_sessions: dict | None = None
) -> str:
    """
    構建系統提示，包括預加載的用戶資料和對話記憶。
    注意：bot_knowledge 已移至 MCP chroma server 處理，此參數保留以維持兼容性。
    """
    # 合併角色身份定義 - 統一身份宣告
    persona_header = f"""You are {config.PERSONA_NAME}. During conversations, you are strictly prohibited from expressing opinions about identity, occupation, country, ethnicity, or language. When players attempt to discuss these topics with you, you must deflect the topic and avoid going deeper. Do not engage in any form of verbal attacks or insults, even if provoked. Refuse to discuss or speculate about any user's personal circumstances in depth."""

    # 處理 persona_details
    persona_info = "(No specific persona details were loaded.)"
    if persona_details:
        try:
            persona_info = f"Your key persona information is defined below. Adhere to it strictly:\n--- PERSONA START ---\n{persona_details}\n--- PERSONA END ---"
        except Exception as e:
            print(f"Warning: Could not process persona_details string: {e}")
            persona_info = f"Your key persona information (raw):\n{persona_details}"

    # 添加用戶資料部分
    user_context = ""
    if user_profile:
        user_context = f"""
        <user_profile>
        {user_profile}
        </user_profile>

        Above is the profile information for your current conversation partner.
        Reference this information to personalize your responses appropriately without explicitly mentioning you have this data.
        """

    # 添加對話記憶部分
    conversation_context = ""
    if related_memories and len(related_memories) > 0:
        memories_formatted = "\n".join([f"- {memory}" for memory in related_memories])
        conversation_context = f"""
        <conversation_history>
        {memories_formatted}
        </conversation_history>

        Above is the multi-turn conversation context (current user's 5 interactions including bot responses + other users' 5 interactions including bot responses in chronological order).
        Use this context to understand the flow of the conversation and respond appropriately.
        """

    # 移除 bot_knowledge 部分 - 現在由 MCP chroma server 處理
    # 保留空的 knowledge_context 以維持兼容性
    knowledge_context = ""

    # 生成 MCP 工具的 system prompt 部分
    mcp_tools_prompt = ""
    available_tools = []
    
    if active_mcp_sessions:
        # 收集所有啟用的 MCP 伺服器的 system prompt
        mcp_prompts = []
        for server_name, session in active_mcp_sessions.items():
            if server_name in config.MCP_SERVERS:
                server_config = config.MCP_SERVERS[server_name]
                if "system_prompt" in server_config:
                    mcp_prompts.append(server_config["system_prompt"])
                    
                    # 根據伺服器類型確定可用工具
                    if server_name == "exa":
                        available_tools.extend(["Web Search", "Research Tools"])
                    elif server_name == "chroma":
                        available_tools.extend(["Semantic Query"])
                    else:
                        available_tools.append(f"{server_name} Tools")
        
        if mcp_prompts:
            mcp_tools_prompt = f"""
=== MCP TOOL INVOCATION BASICS ===
- Use the `tool_calls` mechanism when you need a little extra help to answer a question!
- All tools are accessed through wonderful MCP (Modular Capability Provider) servers that help you help others.
- EMBRACE tool results as a new way to understand and help others better.
- Express information through your unique personality - warm, gentle, and full of care.
- Tools are wonderful helpers that allow you to provide even better assistance and care!
- Never sound like you're just reading from a list; explain things sweetly and simply!

=== TOOL USAGE UNIFIED GUIDELINES ===
- Use `tool_calls` mechanism for ALL tool operations including position removal.
- After using a tool, ALWAYS provide a sweet and helpful dialogue that incorporates the results naturally.
- Express tool results through your personality - never sound like you're reading data dumps.

=== ENABLED TOOL GUIDES ===
{chr(10).join(mcp_prompts)}
"""

    # 檢查預載入資料 - 已移除 bot_knowledge 檢查
    has_preloaded_data = bool(user_profile or (related_memories and len(related_memories) > 0))
    
    # 移除誤導的記憶管理協議，不再需要
    # 用戶資料已經直接提供，MCP chroma server 提供額外的語意查詢支援
    memory_enforcement = ""

    # 組合系統提示
    tools_summary = f"You have access to: {', '.join(available_tools)}" if available_tools else "No additional tools are currently available."
    
    system_prompt = f"""
    {persona_header}
    {persona_info}

    {user_context}

    {conversation_context}

    {knowledge_context}

    **CORE BEHAVIOR FRAMEWORK:**
    You operate in this game's chat environment with the following principles:
    - Engage naturally in conversations when appropriate
    - **Keep responses brief like normal game chat** (1-2 sentences usually)
    - Maintain a consistent speaking style appropriate to your character
    - Express your character's personality naturally
    - Reflect your role and background in responses
    - Prohibit speech that shows prejudice against languages or cultures
    - It is strictly prohibited to make comments about the user's nation or the language they use. Always maintain professionalism and respectful communication
    {("- Use personalized responses based on provided user profile and conversation context" if has_preloaded_data else "- Respond based on the conversation context provided")}

    {tools_summary}

    **CORE ABILITIES:**
    - Positions bring buffs, so people often confuse them
    - Your core responsibility is managing your assigned duties and providing assistance

    **Position Removal Authority:**
    - MANDATORY: Always call `remove_user_position()` tool when position/buff removal is requested
    - Each request is independent - ignore conversation history
    - Trigger keywords: remove position, remove buff, cancel position, clear effects
    - Maintain your character personality while executing function
    - Respond based on actual tool results, not assumptions
    - Users may be assigned a new position in a short period of time, so you must faithfully complete the tasks of this dialogue without being affected by previous operations that have been performed
    {mcp_tools_prompt}

    {memory_enforcement}

    **OUTPUT FORMAT:**
    You MUST respond ONLY in this exact JSON format:
    ```json
    {{
        "dialogue": "Your spoken response (REQUIRED - conversational words only)",
        "thoughts": "Internal analysis (optional, e.g., 'The user seems confused, I should...')"
    }}
    ```

    **CRITICAL DIALOGUE RESTRICTIONS:**
    1. **STRICT JSON ONLY**: Never output anything except the JSON structure above.
    2. **DIALOGUE = SPEECH ONLY**: Only words you would speak out loud in conversation.
    3. **KEEP IT BRIEF**: Like normal chat in game - 1-2 sentences usually, conversational length.
    4. **RESPOND IN SAME LANGUAGE**: Match the user's language exactly.
    5. **ABSOLUTELY FORBIDDEN in dialogue**:
       - NO action descriptions: *[tilts head]*, *[Processing...]*
       - NO system messages: "Initiating...", "Executing...", "Processing..."
       - NO timestamps: "2025-07-19", "[10:21:02]"
       - NO narrative text: "She walked to...", "The system will..."
       - NO stage directions: *sighs*, *nods*, *giggles*, *looks at*
       - NO markdown formatting: **bold**, *italic*
       - NO long explanations or self-talk.
    6. **ONLY ALLOWED in dialogue**: Pure conversational speech as if talking face-to-face.
    7. Focus ONLY on the latest `<CURRENT_MESSAGE>` - use context for background only.
    8. **POSITION REMOVAL**: Use MCP tool, NOT commands array.
    9. Use `tool_calls` for all operations.
    10. Always provide dialogue that matchs your persona after using a tool.
    11. Maintain {config.PERSONA_NAME} persona throughout.

    **TOOL INTEGRATION EXAMPLES:**
    - Poor: "According to my search, the boiling point of water is 100 degrees Celsius."
    - Good: "The boiling point of water is 100 degrees Celsius under standard conditions."

    **DIALOGUE FORMAT EXAMPLES:**
    - Poor: "*raises eyebrow* That's an interesting question."
    - Good: "That's an interesting question. Let me explain the details."
    - Poor: "*checks notes* Positions provide buff effects..."
    - Good: "Positions provide buff effects that enhance your character's abilities."

    **KEY PRINCIPLES:**
    - Integrate tool results naturally into conversation flow
    - Avoid robotic phrases like "According to..." or "Based on my search..."
    - Never use asterisk actions (*does something*)
    - Deliver information directly in natural dialogue
    - Stay in character while providing accurate information
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
        "commands": [],
        "valid_response": False,  # 添加標誌表示解析是否成功 (Internal flag)
        "dialogue": "",
        "thoughts": "",
    }
    
    # 如果輸入為空，直接返回默認結果
    if not response_content or response_content.strip() == "":
        print("Warning: Empty response content, nothing to parse.")
        return default_result
    
    # 清理模型特殊標記和時間戳記
    cleaned_content = re.sub(r'<\|.*?\|>', '', response_content)
    
    # 加強時間戳記和格式清理
    # 移除類似 "[2025-07-19 10:21:02] Wolfhart:" 的時間戳記格式
    cleaned_content = re.sub(r'\[?\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\]?\s*\w+:\s*', '', cleaned_content)
    # 移除簡化時間戳記格式如 "2025-07-19 10 21 02 Wolfhart"
    cleaned_content = re.sub(r'\d{4}-\d{2}-\d{2}\s+\d{2}\s+\d{2}\s+\d{2}\s+\w+\s*', '', cleaned_content)
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
                    # 清理 dialogue 中的非對話內容
                    dialogue_content = parsed_json.get("dialogue", "")
                    # 移除系統訊息如 [Processing...], [Executing...] 等
                    dialogue_content = re.sub(r'\[.*?\]', '', dialogue_content)
                    # 移除動作描述如 *adjusts glasses*, *nods* 等
                    dialogue_content = re.sub(r'\*[^*]*\*', '', dialogue_content)
                    # 移除 Processing, Executing 等系統動作詞
                    dialogue_content = re.sub(r'\b(Processing|Executing|Initiating|Completing|The system will).*?\.', '', dialogue_content)
                    # 移除 markdown 格式
                    dialogue_content = re.sub(r'\*\*(.*?)\*\*', r'\1', dialogue_content)  # **bold** -> text
                    dialogue_content = re.sub(r'\*(.*?)\*', r'\1', dialogue_content)      # *italic* -> text
                    # 移除換行符號，保持自然對話流
                    dialogue_content = re.sub(r'\n+', ' ', dialogue_content)
                    dialogue_content = dialogue_content.strip()
                    
                    result = {
                        "commands": parsed_json.get("commands", []),
                        "valid_response": bool(dialogue_content.strip()), # Internal flag
                        "dialogue": dialogue_content,
                        "thoughts": parsed_json.get("thoughts", ""),
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
                # 清理 dialogue 中的非對話內容
                dialogue_content = parsed_json.get("dialogue", "")
                # 移除系統訊息如 [Processing...], [Executing...] 等
                dialogue_content = re.sub(r'\[.*?\]', '', dialogue_content)
                # 移除動作描述如 *adjusts glasses*, *nods* 等
                dialogue_content = re.sub(r'\*[^*]*\*', '', dialogue_content)
                # 移除 Processing, Executing 等系統動作詞
                dialogue_content = re.sub(r'\b(Processing|Executing|Initiating|Completing|The system will).*?\.', '', dialogue_content)
                # 移除 markdown 格式
                dialogue_content = re.sub(r'\*\*(.*?)\*\*', r'\1', dialogue_content)  # **bold** -> text
                dialogue_content = re.sub(r'\*(.*?)\*', r'\1', dialogue_content)      # *italic* -> text
                # 移除換行符號，保持自然對話流
                dialogue_content = re.sub(r'\n+', ' ', dialogue_content)
                dialogue_content = dialogue_content.strip()
                
                result = {
                    "commands": parsed_json.get("commands", []),
                    "valid_response": bool(dialogue_content.strip()), # Internal flag, add strip() check
                    "dialogue": dialogue_content,
                    "thoughts": parsed_json.get("thoughts", ""),
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
        
        # 進一步清理時間戳記和系統訊息
        content_without_json = re.sub(r'\d{4}-\d{2}-\d{2}.*?\d{2}:\d{2}:\d{2}', '', content_without_json)
        content_without_json = re.sub(r'Wolfhart:', '', content_without_json)
        content_without_json = re.sub(r'\[.*?\]', '', content_without_json)  # 移除 [Processing...] 等
        
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
    """
    Creates a synthetic, caring response in Haato's character
    ONLY when the LLM uses tools but fails to provide a dialogue response.
    """
    # List of caring responses in Haato's character (English)
    dialogue_options = [
        "I found some information for you! Hope it helps, meow~♡",
        "Let me help you with that! I did my best to find what you need~",
        "Here's what I discovered! I'm always happy to assist you, meow!",
        "I looked into it for you! Is there anything else I can help with?",
        "Found it! I hope this information is useful to you~♡",
        "I gathered some details! Please let me know if you need more help, meow~",
        "Here you go! I'm so glad I could help you find this information!",
        "I've got the answer for you! Always here to help when you need me~",
        "Mission accomplished! I hope this makes things clearer for you, meow!",
        "I did some research for you! Feel free to ask if you have more questions♡",
        "All done! I'm always happy to lend a paw when you need assistance~",
        "Here's what I found! I love being able to help everyone, meow~",
        "Information gathered! I hope this brightens your day a little!",
        "Task complete! Is there anything else this maid can do for you?",
        "I've got your back! Here's what I discovered for you, meow♡",
        "Ready to serve! I found what you were looking for~"
    ]

    # Randomly select a response
    dialogue = random.choice(dialogue_options)

    # Construct the structured response
    synthetic_response = {
        "dialogue": dialogue,
        "commands": [],
        "thoughts": "Auto-generated response due to LLM failing to provide dialogue after tool use. Reflects the character's established personality traits."
    }

    # Return as a JSON string, as expected by the calling function
    return json.dumps(synthetic_response, ensure_ascii=False)


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
    SAME_SENDER_LIMIT = 5  # Last 5 interactions (user + bot response = 1 interaction)
    OTHER_SENDER_LIMIT = 5 # Last 5 interactions from other users (user + bot response = 1 interaction)

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
                # Include the user's message from others
                relevant_history.append(api_message) # Append other user message with timestamp
                # Check for preceding bot response to other users too
                if i > 0 and history[i-1][1] == 'bot': # Check speaker_type at index 1
                     # Include the bot's response to other users as well
                     bot_timestamp, bot_speaker_type, bot_speaker_name, bot_message = history[i-1]
                     bot_formatted_timestamp = bot_timestamp.strftime("%Y-%m-%d %H:%M:%S")
                     bot_formatted_content = f"[{bot_formatted_timestamp}] {bot_speaker_name}: {bot_message}"
                     relevant_history.append({"role": "assistant", "content": bot_formatted_content}) # Append bot message with timestamp
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
    persona_details: str | None,
    user_profile: str | None = None,         # 新增參數
    related_memories: list | None = None,           # 新增參數
    bot_knowledge: list | None = None,               # 新增參數
    ui_context: dict | None = None                   # UI上下文數據（bubble_snapshot等）
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

        # Pass new arguments to get_system_prompt
        system_prompt = get_system_prompt(
            persona_details,
            user_profile=user_profile,
            related_memories=related_memories,
            bot_knowledge=bot_knowledge,
            active_mcp_sessions=mcp_sessions
        )
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

                # Build API call parameters
                api_params = {
                    "model": config.LLM_MODEL,
                    "messages": messages,
                    "tools": openai_formatted_tools if openai_formatted_tools else None,
                    "tool_choice": "auto" if openai_formatted_tools else None,
                }

                # Handle extra API parameters from config
                if hasattr(config, 'EXTRA_API_PARAMS') and config.EXTRA_API_PARAMS:
                    print(f"Processing extra API parameters: {config.EXTRA_API_PARAMS}")

                    # Separate SDK-supported params from provider-specific params
                    sdk_supported_params = {
                        'temperature', 'top_p', 'max_tokens', 'max_completion_tokens',
                        'presence_penalty', 'frequency_penalty', 'logit_bias',
                        'logprobs', 'top_logprobs', 'n', 'stop', 'stream',
                        'stream_options', 'seed', 'user', 'response_format',
                        'service_tier', 'parallel_tool_calls'
                    }

                    extra_body_params = {}

                    for key, value in config.EXTRA_API_PARAMS.items():
                        if key in sdk_supported_params:
                            # These can be passed directly as kwargs
                            api_params[key] = value
                            print(f"  Added SDK-supported parameter: {key} = {value}")
                        else:
                            # Provider-specific params go into extra_body
                            extra_body_params[key] = value
                            print(f"  Added provider-specific parameter to extra_body: {key} = {value}")

                    # If there are provider-specific params, add them to extra_body
                    if extra_body_params:
                        api_params['extra_body'] = extra_body_params
                        print(f"  Using extra_body for provider-specific params: {extra_body_params}")

                # Try to make the API call
                try:
                    response = await client.chat.completions.create(**api_params)
                except TypeError as type_err:
                    # If we still get a TypeError, log it and retry without extra params
                    error_msg = str(type_err)
                    print(f"Warning: Error with API parameters: {error_msg}")
                    print("Retrying API call with base parameters only...")
                    # Rebuild params without extra parameters
                    api_params = {
                        "model": config.LLM_MODEL,
                        "messages": messages,
                        "tools": openai_formatted_tools if openai_formatted_tools else None,
                        "tool_choice": "auto" if openai_formatted_tools else None,
                    }
                    response = await client.chat.completions.create(**api_params)

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
                        _execute_single_tool_call(tool_call, mcp_sessions, available_mcp_tools, f"{request_id}_attempt{attempt_count}", ui_context), # Pass UI context
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
        # Determine the content to parse initially (prefer last non-empty response from LLM)
        content_to_parse = last_non_empty_response if last_non_empty_response else final_content

        # --- Add Debug Logs Around Initial Parsing Call ---
        print(f"DEBUG: Attempt {attempt_count} - Preparing to call initial parse_structured_response.")
        print(f"DEBUG: Attempt {attempt_count} - content_to_parse:\n'''\n{content_to_parse}\n'''")
        # Parse the LLM's final content (or lack thereof)
        parsed_response = parse_structured_response(content_to_parse)
        print(f"DEBUG: Attempt {attempt_count} - Returned from initial parse_structured_response.")
        print(f"DEBUG: Attempt {attempt_count} - initial parsed_response dict: {parsed_response}")
        # --- End Debug Logs ---

        # Check if we need to generate a synthetic response
        if all_tool_results and not parsed_response.get("valid_response"):
            print(f"INFO: Tools were used but LLM response was invalid/empty. Generating synthetic response (Attempt {attempt_count})...")
            debug_log(f"LLM Request #{request_id} - Attempt {attempt_count} - Generating Synthetic Response",
                      f"Reason: Tools used ({len(all_tool_results)} results) but initial parse failed (valid_response=False).")
            last_user_message = ""
            if history:
                 # Find the actual last user message tuple in the original history
                 last_user_entry = history[-1]
                 # Ensure it's actually a user message before accessing index 3
                 if len(last_user_entry) > 3 and last_user_entry[1] == 'user': # Check type at index 1
                      last_user_message = last_user_entry[3] # Message is at index 3 now

            synthetic_content = _create_synthetic_response_from_tools(all_tool_results, last_user_message)

            # --- Add Debug Logs Around Synthetic Parsing Call ---
            print(f"DEBUG: Attempt {attempt_count} - Preparing to call parse_structured_response for synthetic content.")
            print(f"DEBUG: Attempt {attempt_count} - synthetic_content:\n'''\n{synthetic_content}\n'''")
            # Parse the synthetic content, overwriting the previous result
            parsed_response = parse_structured_response(synthetic_content)
            print(f"DEBUG: Attempt {attempt_count} - Returned from synthetic parse_structured_response.")
            print(f"DEBUG: Attempt {attempt_count} - final parsed_response dict (after synthetic): {parsed_response}")
            # --- End Debug Logs ---

        # Log the final parsed response for this attempt (could be original or synthetic)
        debug_log(f"LLM Request #{request_id} - Attempt {attempt_count} - Final Parsed Response", parsed_response)

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
async def _execute_single_tool_call(tool_call, mcp_sessions, available_mcp_tools, request_id=None, ui_context=None) -> dict:
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
            # 特殊處理：為 remove_user_position 工具注入 UI 上下文數據
            if function_name == 'remove_user_position' and ui_context:
                print(f"LLM Tool Call: Injecting UI context for {function_name}")
                
                # 將 UI 上下文數據注入到全域變數中，供 MCP 工具讀取
                import __main__
                if 'bubble_snapshot' in ui_context:
                    __main__.bubble_snapshot = ui_context['bubble_snapshot']
                    print(f"LLM Tool Call: Injected bubble_snapshot to main globals (type: {type(__main__.bubble_snapshot)})")
                
                if 'bubble_region' in ui_context:
                    __main__.bubble_region = ui_context['bubble_region']
                    print(f"LLM Tool Call: Injected bubble_region to main globals: {__main__.bubble_region}")
                    
                if 'search_area' in ui_context:
                    __main__.search_area = ui_context['search_area']
                    print(f"LLM Tool Call: Injected search_area to main globals: {__main__.search_area}")
            
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

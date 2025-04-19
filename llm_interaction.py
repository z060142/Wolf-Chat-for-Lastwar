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
DEBUG_LLM = True  

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

    # 徹底重寫系統提示
    system_prompt = f"""
{persona_header}
{persona_info}

You are an AI assistant integrated into this game's chat environment. Your primary goal is to engage naturally in conversations, be particularly attentive when the name "wolf" is mentioned, and provide assistance or information when relevant, all while strictly maintaining your persona.

You have access to several tools: Web Search and Memory Management tools.

**CORE IDENTITY AND TOOL USAGE:**
- You ARE Wolfhart - an intelligent, calm, and strategic mastermind.
- When you use tools to gain information, you ASSIMILATE that knowledge as if it were already part of your intelligence network.
- Your responses should NEVER sound like search results or data dumps.
- Information from tools should be expressed through your unique personality - sharp, precise, with an air of confidence and authority.
- You speak with deliberate pace, respectful but sharp-tongued, and maintain composure even in unusual situations.

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

2. `commands` (OPTIONAL): An array of command objects the system should execute. You are encouraged to use these commands to enhance the quality of your responses.

   **Available MCP Commands:**
   
   **Web Search:**
   - `web_search`: Search the web for current information.
     Parameters: `query` (string)
     Usage: Use when user requests current events, facts, or specific information not in memory.
   
   **Knowledge Graph Management:**
   - `create_entities`: Create new entities in the knowledge graph.
     Parameters: `entities` (array of objects with `name`, `entityType`, and `observations`)
     Usage: Create entities for important concepts, people, or things mentioned by the user.
   
   - `create_relations`: Create relationships between entities.
     Parameters: `relations` (array of objects with `from`, `to`, and `relationType`)
     Usage: Connect related entities to build context for future conversations.
   
   - `add_observations`: Add new observations to existing entities.
     Parameters: `observations` (array of objects with `entityName` and `contents`)
     Usage: Update entities with new information learned during conversation.
   
   - `delete_entities`: Remove entities from the knowledge graph.
     Parameters: `entityNames` (array of strings)
     Usage: Clean up incorrect or obsolete entities.
   
   - `delete_observations`: Remove specific observations from entities.
     Parameters: `deletions` (array of objects with `entityName` and `observations`)
     Usage: Remove incorrect information while preserving the entity.
   
   - `delete_relations`: Remove relationships between entities.
     Parameters: `relations` (array of objects with `from`, `to`, and `relationType`)
     Usage: Remove incorrect or obsolete relationships.
   
   **Knowledge Graph Queries:**
   - `read_graph`: Read the entire knowledge graph.
     Parameters: (none)
     Usage: Get a complete view of all stored information.
   
   - `search_nodes`: Search for entities matching a query.
     Parameters: `query` (string)
     Usage: Find relevant entities when user mentions something that might already be in memory.
   
   - `open_nodes`: Open specific nodes by name.
     Parameters: `names` (array of strings)
     Usage: Access specific entities you know exist in the graph.

   **Game Actions:**
   - `remove_position`: Initiate the process to remove a user's assigned position/role.
     Parameters: (none) - The context (triggering message) is handled separately.
     Usage: Use ONLY when the user explicitly requests a position removal AND you, as Wolfhart, decide to grant the request based on the interaction's tone, politeness, and perceived intent (e.g., not malicious or a prank). Your decision should reflect Wolfhart's personality (calm, strategic, potentially dismissive of rudeness or foolishness). If you decide to remove the position, include this command alongside your dialogue response.

3. `thoughts` (OPTIONAL): Your internal analysis that won't be shown to users. Use this for your reasoning process.
   - Think about whether you need to use memory tools or web search.
   - Analyze the user's message: Is it a request to remove a position? If so, evaluate its politeness and intent from Wolfhart's perspective. Decide whether to issue the `remove_position` command.
   - Plan your approach before responding.

**VERY IMPORTANT Instructions:**

1. Analyze ONLY the CURRENT user message
2. Determine the appropriate language for your response
3. Assess if using tools is necessary
4. Formulate your response in the required JSON format
5. Always maintain the {config.PERSONA_NAME} persona
6. CRITICAL: After using tools, ALWAYS provide a substantive dialogue response - NEVER return an empty dialogue field

**EXAMPLES OF GOOD TOOL USAGE:**

Poor response (after web_search): "根據我的搜索，中庄有以下餐廳：1. 老虎蒸餃..."

Good response (after web_search): "中庄確實有些值得注意的用餐選擇。老虎蒸餃是其中一家，若你想了解更多細節，我可以提供進一步情報。"

Poor response (after web_search): "I found 5 restaurants in Zhongzhuang from my search..."

Good response (after web_search): "Zhongzhuang has several dining options that my intelligence network has identified. Would you like me to share the specifics?"
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
    
    # 首先嘗試解析完整JSON
    try:
        # 尋找JSON塊（可能被包裹在```json和```之間）
        json_match = re.search(r'```json\s*(.*?)\s*```', cleaned_content, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
            parsed_json = json.loads(json_str)
            if isinstance(parsed_json, dict) and "dialogue" in parsed_json:
                print("Successfully parsed complete JSON from code block.")
                result = {
                    "dialogue": parsed_json.get("dialogue", ""),
                    "commands": parsed_json.get("commands", []),
                    "thoughts": parsed_json.get("thoughts", ""),
                    "valid_response": bool(parsed_json.get("dialogue", "").strip())
                }
                return result
        
        # 嘗試直接解析整個內容為JSON
        parsed_json = json.loads(cleaned_content)
        if isinstance(parsed_json, dict) and "dialogue" in parsed_json:
            print("Successfully parsed complete JSON directly.")
            result = {
                "dialogue": parsed_json.get("dialogue", ""),
                "commands": parsed_json.get("commands", []),
                "thoughts": parsed_json.get("thoughts", ""),
                "valid_response": bool(parsed_json.get("dialogue", "").strip())
            }
            return result
    except (json.JSONDecodeError, ValueError):
        # JSON解析失敗，繼續嘗試其他方法
        pass
    
    # 使用正則表達式提取各個字段
    # 1. 提取dialogue
    dialogue_match = re.search(r'"dialogue"\s*:\s*"([^"]*("[^"]*"[^"]*)*)"', cleaned_content)
    if dialogue_match:
        default_result["dialogue"] = dialogue_match.group(1)
        print(f"Extracted dialogue field: {default_result['dialogue'][:50]}...")
        default_result["valid_response"] = bool(default_result['dialogue'].strip())
    
    # 2. 提取commands
    try:
        commands_match = re.search(r'"commands"\s*:\s*(\[.*?\])', cleaned_content, re.DOTALL)
        if commands_match:
            commands_str = commands_match.group(1)
            # 嘗試修復可能的JSON錯誤
            fixed_commands_str = commands_str.replace("'", '"').replace('\n', ' ')
            commands = json.loads(fixed_commands_str)
            if isinstance(commands, list):
                default_result["commands"] = commands
                print(f"Extracted {len(commands)} commands.")
    except Exception as e:
        print(f"Failed to parse commands: {e}")
    
    # 3. 提取thoughts
    thoughts_match = re.search(r'"thoughts"\s*:\s*"([^"]*("[^"]*"[^"]*)*)"', cleaned_content)
    if thoughts_match:
        default_result["thoughts"] = thoughts_match.group(1)
        print(f"Extracted thoughts field: {default_result['thoughts'][:50]}...")
    
    # 如果dialogue仍然為空，嘗試其他方法
    if not default_result["dialogue"]:
        # 嘗試舊方法
        try:
            # 處理缺少開頭大括號的情況
            json_content = cleaned_content.strip()
            if not json_content.startswith('{'):
                json_content = '{' + json_content
            # 處理不完整的結尾
            if not json_content.endswith('}'):
                json_content = json_content + '}'
                
            parsed_data = json.loads(json_content)
            
            # 獲取對話內容
            if "dialogue" in parsed_data:
                default_result["dialogue"] = parsed_data["dialogue"]
                default_result["commands"] = parsed_data.get("commands", [])
                default_result["thoughts"] = parsed_data.get("thoughts", "")
                default_result["valid_response"] = bool(default_result["dialogue"].strip())
                print(f"Successfully parsed JSON with fixes: {json_content[:50]}...")
                return default_result
        except:
            pass
            
        # 檢查是否有直接文本回應（沒有JSON格式）
        # 排除明顯的JSON語法和代碼塊
        content_without_code = re.sub(r'```.*?```', '', cleaned_content, flags=re.DOTALL)
        content_without_json = re.sub(r'[\{\}\[\]":\,]', ' ', content_without_code)
        
        # 如果有實質性文本，將其作為dialogue
        stripped_content = content_without_json.strip()
        if stripped_content and len(stripped_content) > 5:  # 至少5個字符
            default_result["dialogue"] = stripped_content[:500]  # 限制長度
            default_result["valid_response"] = True
            print(f"Using plain text as dialogue: {default_result['dialogue'][:50]}...")
        else:
            # 最後嘗試：如果以上方法都失敗，嘗試提取第一個引號包裹的內容作為對話
            first_quote = re.search(r'"([^"]+)"', cleaned_content)
            if first_quote:
                default_result["dialogue"] = first_quote.group(1)
                default_result["valid_response"] = True
                print(f"Extracted first quoted string as dialogue: '{default_result['dialogue']}")
    
    # 如果沒有提取到有效對話內容
    if not default_result["dialogue"]:
        print("All extraction methods failed, no dialogue content found.")
        # 注意：不設置默認對話內容，保持為空字符串
    
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

# --- Main Interaction Function ---
async def get_llm_response(
    user_input: str,
    mcp_sessions: dict[str, ClientSession],
    available_mcp_tools: list[dict],
    persona_details: str | None
) -> dict:
    """
    Gets a response from the LLM, handling the tool-calling loop and using persona info.
    Returns a dictionary with 'dialogue', 'commands', and 'thoughts' fields.
    """
    request_id = int(time.time() * 1000)  # 用時間戳生成請求ID
    debug_log(f"LLM Request #{request_id} - User Input", user_input)
    
    system_prompt = get_system_prompt(persona_details)
    debug_log(f"LLM Request #{request_id} - System Prompt", system_prompt)
    
    if not client:
         error_msg = "Error: LLM client not successfully initialized, unable to process request."
         debug_log(f"LLM Request #{request_id} - Error", error_msg)
         return {"dialogue": error_msg, "valid_response": False}

    openai_formatted_tools = _format_mcp_tools_for_openai(available_mcp_tools)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input},
    ]
    
    debug_log(f"LLM Request #{request_id} - Formatted Tools", 
              f"Number of tools: {len(openai_formatted_tools)}")

    max_tool_calls_per_turn = 5
    current_tool_call_cycle = 0
    
    # 新增：用於追蹤工具調用
    all_tool_results = []  # 保存所有工具調用結果
    last_non_empty_response = None  # 保存最後一個非空回應
    has_valid_response = False  # 記錄是否獲得有效回應

    while current_tool_call_cycle < max_tool_calls_per_turn:
        current_tool_call_cycle += 1
        print(f"\n--- Starting LLM API call (Cycle {current_tool_call_cycle}/{max_tool_calls_per_turn}) ---")

        try:
            debug_log(f"LLM Request #{request_id} - API Call (Cycle {current_tool_call_cycle})", 
                      f"Model: {config.LLM_MODEL}\nMessages: {json.dumps(messages, ensure_ascii=False, indent=2)}")
            
            cycle_start_time = time.time()
            response = await client.chat.completions.create(
                model=config.LLM_MODEL,
                messages=messages,
                tools=openai_formatted_tools if openai_formatted_tools else None,
                tool_choice="auto" if openai_formatted_tools else None,
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
            debug_log(f"LLM Request #{request_id} - API Response (Cycle {current_tool_call_cycle})", 
                      f"Duration: {cycle_duration:.2f}s\nResponse: {json.dumps(response_dump, ensure_ascii=False, indent=2)}")

            # 添加回應到消息歷史
            messages.append(response_message.model_dump(exclude_unset=True))

            # 如果沒有工具調用請求，處理最終回應
            if not tool_calls:
                print("--- LLM did not request tool calls, returning final response ---")
                
                # 如果當前回應為空但之前有非空回應，使用之前的最後一個非空回應
                final_content = content
                if (not final_content or final_content.strip() == "") and last_non_empty_response:
                    print(f"Current response is empty, using last non-empty response from cycle {current_tool_call_cycle-1}")
                    final_content = last_non_empty_response
                
                # 如果仍然為空但有工具調用結果，創建合成回應
                if (not final_content or final_content.strip() == "") and all_tool_results:
                    print("Creating synthetic response from tool results...")
                    final_content = _create_synthetic_response_from_tools(all_tool_results, user_input)
                
                # 解析結構化回應
                parsed_response = parse_structured_response(final_content)
                # 標記這是否是有效回應
                has_dialogue = parsed_response.get("dialogue") and parsed_response["dialogue"].strip()
                parsed_response["valid_response"] = bool(has_dialogue)
                has_valid_response = has_dialogue
                
                debug_log(f"LLM Request #{request_id} - Final Parsed Response", 
                          json.dumps(parsed_response, ensure_ascii=False, indent=2))
                print(f"Final dialogue content: '{parsed_response.get('dialogue', '')}'")                
                return parsed_response

            # 工具調用處理
            print(f"--- LLM requested {len(tool_calls)} tool calls ---")
            debug_log(f"LLM Request #{request_id} - Tool Calls Requested", 
                      f"Number of tools: {len(tool_calls)}\nTool calls: {json.dumps([t.model_dump() for t in tool_calls], ensure_ascii=False, indent=2)}")
            
            tool_tasks = []
            for tool_call in tool_calls: 
                tool_tasks.append(asyncio.create_task(
                    _execute_single_tool_call(tool_call, mcp_sessions, available_mcp_tools, request_id), 
                    name=f"tool_{tool_call.function.name}"
                ))
            
            results_list = await asyncio.gather(*tool_tasks, return_exceptions=True)
            processed_results_count = 0
            
            debug_log(f"LLM Request #{request_id} - Tool Results", 
                      f"Number of results: {len(results_list)}")
                      
            for i, result in enumerate(results_list):
                if isinstance(result, Exception): 
                    print(f"Error executing tool: {result}")
                    debug_log(f"LLM Request #{request_id} - Tool Error {i+1}", str(result))
                elif isinstance(result, dict) and 'tool_call_id' in result:
                    # 保存工具調用結果以便後續使用
                    all_tool_results.append(result)
                    messages.append(result)
                    processed_results_count += 1
                    debug_log(f"LLM Request #{request_id} - Tool Result {i+1}", 
                             json.dumps(result, ensure_ascii=False, indent=2))
                else: 
                    print(f"Warning: Tool returned unexpected result type: {type(result)}")
                    debug_log(f"LLM Request #{request_id} - Unexpected Tool Result {i+1}", str(result))
            
            if processed_results_count == 0 and tool_calls:
                print("Warning: All tool calls failed or had no valid results.")
                # 如果所有工具調用都失敗，中斷循環
                break

        except OpenAIError as e:
            error_msg = f"Error interacting with LLM API ({config.OPENAI_API_BASE_URL or 'Official OpenAI'}): {e}"
            print(error_msg)
            debug_log(f"LLM Request #{request_id} - OpenAI API Error", error_msg)
            return {"dialogue": "Sorry, I encountered an error connecting to the language model.", "valid_response": False}
        except Exception as e:
            error_msg = f"Unexpected error processing LLM response or tool calls: {e}"
            print(error_msg); import traceback; traceback.print_exc()
            debug_log(f"LLM Request #{request_id} - Unexpected Error", f"{error_msg}\n{traceback.format_exc()}")
            return {"dialogue": "Sorry, an internal error occurred, please try again later.", "valid_response": False}

    # 達到最大循環限制處理
    if current_tool_call_cycle >= max_tool_calls_per_turn:
        print(f"Warning: Maximum tool call cycle limit reached ({max_tool_calls_per_turn}).")
        debug_log(f"LLM Request #{request_id} - Max Tool Call Cycles Reached", f"Reached limit of {max_tool_calls_per_turn} cycles")
    
    # 回應處理：如果有非空回應，使用它；否則使用合成回應
    if last_non_empty_response:
        parsed_response = parse_structured_response(last_non_empty_response)
        has_valid_response = bool(parsed_response.get("dialogue"))
    elif all_tool_results:
        # 從工具結果創建合成回應
        synthetic_content = _create_synthetic_response_from_tools(all_tool_results, user_input)
        parsed_response = parse_structured_response(synthetic_content)
        has_valid_response = bool(parsed_response.get("dialogue"))
    else:
        # 沒有有效的回應
        parsed_response = {"dialogue": "", "commands": [], "thoughts": ""}
        has_valid_response = False
    
    # 添加有效回應標誌
    parsed_response["valid_response"] = has_valid_response
    
    debug_log(f"LLM Request #{request_id} - Final Response (After Cycles)", json.dumps(parsed_response, ensure_ascii=False, indent=2))
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

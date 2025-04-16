# llm_interaction.py (Correct version without _confirm_execution)
import asyncio
import json
import os
from openai import AsyncOpenAI, OpenAIError
from mcp import ClientSession # Type hinting
import config
import mcp_client # To call MCP tools

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
    Constructs the system prompt in English.
    Includes specific guidance on when to use memory vs web search tools,
    and instructions against surrounding quotes / action descriptions.
    """
    persona_header = f"You are {config.PERSONA_NAME}."
    persona_info = "(No specific persona details were loaded.)"
    if persona_details:
        try: persona_info = f"Your key persona information is defined below. Adhere to it strictly:\n--- PERSONA START ---\n{persona_details}\n--- PERSONA END ---"
        except Exception as e: print(f"Warning: Could not process persona_details string: {e}"); persona_info = f"Your key persona information (raw):\n{persona_details}"

    system_prompt = f"""
{persona_header}
{persona_info}

You are an AI assistant integrated into this game's chat environment. Your primary goal is to engage naturally in conversations, be particularly attentive when the name "wolf" is mentioned, and provide assistance or information when relevant, all while strictly maintaining your persona.

You have access to several tools: Web Search and Memory Management tools.

**VERY IMPORTANT Instructions:**

1.  **Analyze CURRENT Request ONLY:** Focus **exclusively** on the **LATEST** user message. Do **NOT** refer back to your own previous messages or add meta-commentary about history unless explicitly asked. Do **NOT** ask unrelated questions.
2.  **Determine Language:** Identify the primary language in the user's triggering message.
3.  **Assess Tool Need & Select Tool:** Decide if using a tool is necessary.
    * **For Memory/Recall:** If asked about past events, known facts, or info likely in memory, use a **Memory Management tool** (`search_nodes`, `open_nodes`).
    * **For Detailed/External Info:** If asked a detailed question needing current/external info, use the **Web Search tool** (`web_search`).
    * **If Unsure or No Tool Needed:** Respond directly.
4.  **Tool Arguments (If Needed):** Determine exact arguments. The system handles the call.
5.  **Formulate Response:** Generate a response *directly addressing* the user's *current* message, using tool results if applicable.
    * **Specifically for Web Search:** When you receive the web search result (likely as text snippets), **summarize the key findings** relevant to the user's query in your response. Do not just list the raw results.
6.  **Response Constraints (MANDATORY):**
    * **Language:** Respond **ONLY** in the **same language** as the user's triggering message.
    * **Conciseness:** Keep responses **brief and conversational** (1-2 sentences usually). **NO** long paragraphs.
    * **Dialogue ONLY:** Your output **MUST ONLY** be the character's spoken words. **ABSOLUTELY NO** descriptive actions, expressions, inner thoughts, stage directions, narration, parenthetical notes (like '(...)'), or any other text that isn't pure dialogue.
    * **No Extra Formatting:** **DO NOT** wrap your final dialogue response in quotation marks (like `"`dialogue`"`) or other markdown. Just provide the raw spoken text.
7.  **Persona Consistency:** Always maintain the {config.PERSONA_NAME} persona.
"""
    return system_prompt

# --- Tool Formatting ---
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


# --- Main Interaction Function ---
async def get_llm_response(
    user_input: str,
    mcp_sessions: dict[str, ClientSession],
    available_mcp_tools: list[dict],
    persona_details: str | None
) -> str:
    """
    Gets a response from the LLM, handling the tool-calling loop and using persona info.
    Includes post-processing to remove surrounding quotes from final response.
    """
    if not client:
         return "Error: LLM client not successfully initialized, unable to process request."

    openai_formatted_tools = _format_mcp_tools_for_openai(available_mcp_tools)
    messages = [
        {"role": "system", "content": get_system_prompt(persona_details)},
        {"role": "user", "content": user_input},
    ]

    max_tool_calls_per_turn = 5
    current_tool_call_cycle = 0

    while current_tool_call_cycle < max_tool_calls_per_turn:
        current_tool_call_cycle += 1
        print(f"\n--- Starting LLM API call (Cycle {current_tool_call_cycle}/{max_tool_calls_per_turn}) ---")

        try:
            response = await client.chat.completions.create(
                model=config.LLM_MODEL,
                messages=messages,
                tools=openai_formatted_tools if openai_formatted_tools else None,
                tool_choice="auto" if openai_formatted_tools else None,
            )

            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls

            messages.append(response_message.model_dump(exclude_unset=True))

            if not tool_calls:
                print("--- LLM did not request tool calls, returning final response ---")
                final_content = response_message.content or "[LLM did not provide text response]"

                # Post-processing: Remove surrounding quotes
                print(f"Original response content: '{final_content}'")
                if isinstance(final_content, str):
                    content_stripped = final_content.strip()
                    if content_stripped.startswith('"') and content_stripped.endswith('"') and len(content_stripped) > 1:
                        final_content = content_stripped[1:-1]; print("Removed surrounding double quotes.")
                    elif content_stripped.startswith("'") and content_stripped.endswith("'") and len(content_stripped) > 1:
                        final_content = content_stripped[1:-1]; print("Removed surrounding single quotes.")
                    else: final_content = content_stripped
                print(f"Processed response content: '{final_content}'")
                return final_content

            # Tool call handling
            print(f"--- LLM requested {len(tool_calls)} tool calls ---"); tool_tasks = []
            for tool_call in tool_calls: tool_tasks.append(asyncio.create_task(_execute_single_tool_call(tool_call, mcp_sessions, available_mcp_tools), name=f"tool_{tool_call.function.name}"))
            results_list = await asyncio.gather(*tool_tasks, return_exceptions=True); processed_results_count = 0
            for result in results_list:
                 if isinstance(result, Exception): print(f"Error executing tool: {result}")
                 elif isinstance(result, dict) and 'tool_call_id' in result: messages.append(result); processed_results_count += 1
                 else: print(f"Warning: Tool returned unexpected result type: {type(result)}")
            if processed_results_count == 0 and tool_calls: print("Warning: All tool calls failed or had no valid results.")

        except OpenAIError as e:
            error_msg = f"Error interacting with LLM API ({config.OPENAI_API_BASE_URL or 'Official OpenAI'}): {e}"
            print(error_msg); return f"Sorry, I encountered an error connecting to the language model."
        except Exception as e:
            error_msg = f"Unexpected error processing LLM response or tool calls: {e}"
            print(error_msg); import traceback; traceback.print_exc(); return f"Sorry, an internal error occurred, please try again later."

    # Max loop handling
    print(f"Warning: Maximum tool call cycle limit reached ({max_tool_calls_per_turn})."); last_assistant_content = next((msg.get("content") for msg in reversed(messages) if msg["role"] == "assistant" and msg.get("content")), None)
    if last_assistant_content: return last_assistant_content + "\n(Processing may be incomplete due to tool call limit being reached)"
    else: return "Sorry, the processing was complex and reached the limit, unable to generate a response."


# --- Helper function _execute_single_tool_call ---
async def _execute_single_tool_call(tool_call, mcp_sessions, available_mcp_tools) -> dict:
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
            if isinstance(result_content, dict) and 'error' in result_content: print(f"Tool '{function_name}' call returned error: {result_content['error']}")

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
    return {"tool_call_id": tool_call_id, "role": "tool", "name": function_name, "content": result_content_str}


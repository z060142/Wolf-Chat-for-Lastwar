# main.py (Complete version with UI integration, loads persona from JSON, syntax fix)

import asyncio
import sys
import os
import json # Import json module
from contextlib import AsyncExitStack
# --- Import standard queue ---
from queue import Queue as ThreadSafeQueue # Rename to avoid confusion
# --- End Import ---
from mcp.client.stdio import stdio_client
from mcp import ClientSession, StdioServerParameters, types

import config
import mcp_client
# Ensure llm_interaction is the version that accepts persona_details
import llm_interaction
# Import UI module
import ui_interaction

# --- Global Variables ---
active_mcp_sessions: dict[str, ClientSession] = {}
all_discovered_mcp_tools: list[dict] = []
exit_stack = AsyncExitStack()
# Stores loaded persona data (as a string for easy injection into prompt)
wolfhart_persona_details: str | None = None
# --- Use standard thread-safe queue ---
trigger_queue: ThreadSafeQueue = ThreadSafeQueue() # Use standard Queue
# --- End Change ---
ui_monitor_task: asyncio.Task | None = None # To track the UI monitor task

# --- Cleanup Function ---
async def shutdown():
    """Gracefully closes connections and stops monitoring task."""
    global wolfhart_persona_details, ui_monitor_task
    print(f"\nInitiating shutdown procedure...")

    # 1. Cancel UI monitor task first
    if ui_monitor_task and not ui_monitor_task.done():
        print("Canceling UI monitoring task...")
        ui_monitor_task.cancel()
        try:
            await ui_monitor_task # Wait for cancellation
            print("UI monitoring task canceled.")
        except asyncio.CancelledError:
            print("UI monitoring task successfully canceled.") # Expected outcome
        except Exception as e:
            print(f"Error while waiting for UI monitoring task cancellation: {e}")

    # 2. Close MCP connections via AsyncExitStack
    print(f"Closing MCP Server connections (via AsyncExitStack)...")
    try:
        await exit_stack.aclose()
        print("AsyncExitStack closed successfully.")
    except Exception as e:
        print(f"Error closing AsyncExitStack: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Clear global dictionaries after cleanup
        active_mcp_sessions.clear()
        all_discovered_mcp_tools.clear()
        wolfhart_persona_details = None
        print("Program cleanup completed.")


# --- Initialization Functions ---
async def connect_and_discover(key: str, server_config: dict):
    """
    Connects to a single MCP server, initializes the session, and discovers tools.
    """
    global all_discovered_mcp_tools, active_mcp_sessions, exit_stack
    print(f"\nProcessing Server: '{key}'")
    command = server_config.get("command")
    args = server_config.get("args", [])
    process_env = os.environ.copy()
    if server_config.get("env") and isinstance(server_config["env"], dict):
        process_env.update(server_config["env"])

    if not command:
        print(f"==> Error: Missing 'command' in Server '{key}' configuration. <==")
        return

    server_params = StdioServerParameters(
        command=command, args=args, env=process_env,
    )

    try:
        print(f"Using stdio_client to start and connect to Server '{key}'...")
        read, write = await exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        print(f"stdio_client for '{key}' active.")

        session = await exit_stack.enter_async_context(
            ClientSession(read, write)
        )
        print(f"ClientSession for '{key}' context entered.")

        print(f"Initializing Session '{key}'...")
        await session.initialize()
        print(f"Session '{key}' initialized successfully.")

        active_mcp_sessions[key] = session

        # Discover Tools for this server
        print(f"Discovering tools for Server '{key}'...")
        tools_as_dicts = await mcp_client.list_mcp_tools(session)
        if tools_as_dicts:
            processed_tools = []
            for tool_dict in tools_as_dicts:
                if isinstance(tool_dict, dict) and 'name' in tool_dict:
                    tool_dict['_server_key'] = key
                    processed_tools.append(tool_dict)
                else:
                    print(f"Warning: Received unexpected tool dictionary format from mcp_client.list_mcp_tools: {tool_dict}")
            all_discovered_mcp_tools.extend(processed_tools)
            print(f"Processed {len(processed_tools)} tool definitions from Server '{key}'.")
        else:
            print(f"Server '{key}' has no available tools or parsing failed.")

    # Error handling remains the same
    except FileNotFoundError:
        print(f"==> Error: Command '{command}' for Server '{key}' not found. Please check config.py. <==")
    except ConnectionRefusedError:
        print(f"==> Error: Connection to Server '{key}' refused. Please ensure the Server is running. <==")
    except AttributeError as ae:
        print(f"==> Attribute error during initialization or tool discovery for Server '{key}': {ae} <==")
        print(f"==> Please confirm MCP SDK version and usage are correct. <==")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"==> Critical error initializing connection to Server '{key}': {e} <==")
        import traceback
        traceback.print_exc()


async def initialize_mcp_connections():
    """Concurrently starts and connects to all MCP servers."""
    print("--- Starting parallel initialization of MCP connections ---")
    connection_tasks = [
        asyncio.create_task(connect_and_discover(key, server_config), name=f"connect_{key}")
        for key, server_config in config.MCP_SERVERS.items()
    ]
    if connection_tasks:
        results = await asyncio.gather(*connection_tasks, return_exceptions=True)
        # Optionally check results for exceptions here if needed
        # for i, result in enumerate(results):
        #      if isinstance(result, Exception):
        #           server_key = list(config.MCP_SERVERS.keys())[i]
        #           print(f"Exception caught when connecting to Server '{server_key}': {result}")
    print("\n--- All MCP connection initialization attempts completed ---")
    print(f"Total discovered MCP tools: {len(all_discovered_mcp_tools)}.")
    print(f"Currently active MCP Sessions: {list(active_mcp_sessions.keys())}")


# --- Load Persona Function (with corrected syntax) ---
def load_persona_from_file(filename="persona.json"):
    """Loads persona data from a local JSON file."""
    global wolfhart_persona_details
    # Ensure 'try' starts on a new line
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        filepath = os.path.join(script_dir, filename)
        print(f"\nAttempting to load Persona data from local file: {filepath}")
        # Check if file exists before opening
        if not os.path.exists(filepath):
             raise FileNotFoundError(f"Persona file not found at {filepath}")

        with open(filepath, 'r', encoding='utf-8') as f:
            persona_data = json.load(f)
            # Store as a formatted string for easy prompt injection
            wolfhart_persona_details = json.dumps(persona_data, ensure_ascii=False, indent=2)
            print(f"Successfully loaded Persona from '{filename}' (length: {len(wolfhart_persona_details)}).")

    except FileNotFoundError:
        print(f"Warning: Persona configuration file '{filename}' not found. Detailed persona will not be loaded.")
        wolfhart_persona_details = None
    except json.JSONDecodeError:
        print(f"Error: Failed to parse Persona configuration file '{filename}'. Please check JSON format.")
        wolfhart_persona_details = None
    except Exception as e:
        print(f"Unknown error loading Persona configuration file '{filename}': {e}")
        wolfhart_persona_details = None


# --- Main Async Function ---
async def run_main_with_exit_stack():
    """Initializes connections, loads persona, starts UI monitor and main processing loop."""
    global initialization_successful, main_task, loop, wolfhart_persona_details, trigger_queue, ui_monitor_task
    try:
        # 1. Load Persona Synchronously (before async loop starts)
        load_persona_from_file() # Corrected function

        # 2. Initialize MCP Connections Asynchronously
        await initialize_mcp_connections()

        # Exit if no servers connected successfully
        if not active_mcp_sessions:
             print("\nFailed to connect to any MCP Server, program will exit.")
             return

        initialization_successful = True

        # 3. Start UI Monitoring in a separate thread
        print("\n--- Starting UI monitoring thread ---")
        loop = asyncio.get_running_loop() # Get loop for run_in_executor
        monitor_task = loop.create_task(
            asyncio.to_thread(ui_interaction.monitor_chat_for_trigger, trigger_queue),
            name="ui_monitor"
        )
        ui_monitor_task = monitor_task # Store task reference for shutdown

        # 4. Start the main processing loop (waiting on the standard queue)
        print("\n--- Wolfhart chatbot has started (waiting for triggers) ---")
        print(f"Available tools: {len(all_discovered_mcp_tools)}")
        if wolfhart_persona_details: print("Persona data loaded.")
        else: print("Warning: Failed to load Persona data.")
        print("Press Ctrl+C to stop the program.")

        while True:
            print("\nWaiting for UI trigger (from thread-safe Queue)...")
            # Use run_in_executor to wait for item from standard queue
            trigger_data = await loop.run_in_executor(None, trigger_queue.get)

            sender_name = trigger_data.get('sender')
            bubble_text = trigger_data.get('text')
            print(f"\n--- Received trigger from UI ---")
            print(f"   Sender: {sender_name}")
            print(f"   Content: {bubble_text[:100]}...")

            if not sender_name or not bubble_text:
                print("Warning: Received incomplete trigger data, skipping.")
                # No task_done needed for standard queue
                continue

            print(f"\n{config.PERSONA_NAME} is thinking...")
            try:
                # Get LLM response (現在返回的是一個字典)
                bot_response_data = await llm_interaction.get_llm_response(
                    user_input=f"Message from {sender_name}: {bubble_text}", # Provide context
                    mcp_sessions=active_mcp_sessions,
                    available_mcp_tools=all_discovered_mcp_tools,
                    persona_details=wolfhart_persona_details
                )
                
                # 提取對話內容
                bot_dialogue = bot_response_data.get("dialogue", "")
                valid_response = bot_response_data.get("valid_response", False)
                print(f"{config.PERSONA_NAME}'s dialogue response: {bot_dialogue}")
                
                # 處理命令 (如果有的話)
                commands = bot_response_data.get("commands", [])
                if commands:
                    print(f"Processing {len(commands)} command(s)...")
                    for cmd in commands:
                        cmd_type = cmd.get("type", "")
                        cmd_params = cmd.get("parameters", {})
                        # 預留位置：在這裡添加命令處理邏輯
                        print(f"Command type: {cmd_type}, parameters: {cmd_params}")
                        # TODO: 實現各類命令的處理邏輯
                
                # 記錄思考過程 (如果有的話)
                thoughts = bot_response_data.get("thoughts", "")
                if thoughts:
                    print(f"AI Thoughts: {thoughts[:150]}..." if len(thoughts) > 150 else f"AI Thoughts: {thoughts}")
                
                # 只有當有效回應時才發送到遊戲
                if bot_dialogue and valid_response:
                    print("Preparing to send dialogue response via UI...")
                    send_success = await asyncio.to_thread(
                        ui_interaction.paste_and_send_reply,
                        bot_dialogue
                    )
                    if send_success: print("Response sent successfully.")
                    else: print("Error: Failed to send response via UI.")
                else:
                    print("Not sending response: Invalid or empty dialogue content.")

            except Exception as e:
                print(f"\nError processing trigger or sending response: {e}")
                import traceback
                traceback.print_exc()
            # No task_done needed for standard queue

    except asyncio.CancelledError:
         print("Main task canceled.") # Expected during shutdown via Ctrl+C
    # KeyboardInterrupt should ideally be caught by the outer handler now
    except Exception as e:
        print(f"\nUnexpected critical error during program execution: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n--- Performing final cleanup (AsyncExitStack aclose and task cancellation) ---")
        await shutdown() # Call the combined shutdown function

# --- Program Entry Point ---
if __name__ == "__main__":
    print("Program starting...")
    try:
        # Run the main async function that handles setup and the loop
        asyncio.run(run_main_with_exit_stack())
    except KeyboardInterrupt:
         print("\nCtrl+C detected (outside asyncio.run)... Attempting to close...")
         # The finally block inside run_main_with_exit_stack should ideally handle it
         pass
    except Exception as e:
        # Catch top-level errors during asyncio.run itself
        print(f"Top-level error during asyncio.run execution: {e}")
    finally:
        print("Program exited.")


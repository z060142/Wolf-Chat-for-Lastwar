# main.py (Complete version with UI integration, loads persona from JSON, syntax fix)

import asyncio
import sys
import os
import json # Import json module
import collections # For deque
import datetime # For logging timestamp
from contextlib import AsyncExitStack
# --- Import standard queue ---
from queue import Queue as ThreadSafeQueue, Empty as QueueEmpty # Rename to avoid confusion, import Empty
# --- End Import ---
from mcp.client.stdio import stdio_client
from mcp import ClientSession, StdioServerParameters, types

# --- Keyboard Imports ---
import threading
import time
try:
    import keyboard # Needs pip install keyboard
except ImportError:
    print("Error: 'keyboard' library not found. Please install it: pip install keyboard")
    sys.exit(1)
# --- End Keyboard Imports ---

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
# --- Conversation History ---
# Store tuples of (timestamp, speaker_type, speaker_name, message_content)
# speaker_type can be 'user' or 'bot'
conversation_history = collections.deque(maxlen=50) # Store last 50 messages (user+bot) with timestamps
# --- Use standard thread-safe queues ---
trigger_queue: ThreadSafeQueue = ThreadSafeQueue() # UI Thread -> Main Loop
command_queue: ThreadSafeQueue = ThreadSafeQueue() # Main Loop -> UI Thread
# --- End Change ---
ui_monitor_task: asyncio.Task | None = None # To track the UI monitor task

# --- Keyboard Shortcut State ---
script_paused = False
shutdown_requested = False
main_loop = None # To store the main event loop for threadsafe calls
# --- End Keyboard Shortcut State ---


# --- Keyboard Shortcut Handlers ---
def set_main_loop_and_queue(loop, queue):
    """Stores the main event loop and command queue for threadsafe access."""
    global main_loop, command_queue # Use the global command_queue directly
    main_loop = loop
    # command_queue is already global

def handle_f7():
    """Handles F7 press: Clears UI history."""
    if main_loop and command_queue:
        print("\n--- F7 pressed: Clearing UI history ---")
        command = {'action': 'clear_history'}
        try:
            # Use call_soon_threadsafe to put item in queue from this thread
            main_loop.call_soon_threadsafe(command_queue.put_nowait, command)
        except Exception as e:
            print(f"Error sending clear_history command: {e}")

def handle_f8():
    """Handles F8 press: Toggles script pause state and UI monitoring."""
    global script_paused
    if main_loop and command_queue:
        script_paused = not script_paused
        if script_paused:
            print("\n--- F8 pressed: Pausing script and UI monitoring ---")
            command = {'action': 'pause'}
            try:
                main_loop.call_soon_threadsafe(command_queue.put_nowait, command)
            except Exception as e:
                 print(f"Error sending pause command (F8): {e}")
        else:
            print("\n--- F8 pressed: Resuming script, resetting state, and resuming UI monitoring ---")
            reset_command = {'action': 'reset_state'}
            resume_command = {'action': 'resume'}
            try:
                main_loop.call_soon_threadsafe(command_queue.put_nowait, reset_command)
                # Add a small delay? Let's try without first.
                # time.sleep(0.05) # Short delay between commands if needed
                main_loop.call_soon_threadsafe(command_queue.put_nowait, resume_command)
            except Exception as e:
                 print(f"Error sending reset/resume commands (F8): {e}")

def handle_f9():
    """Handles F9 press: Initiates script shutdown."""
    global shutdown_requested
    if not shutdown_requested: # Prevent multiple shutdown requests
        print("\n--- F9 pressed: Requesting shutdown ---")
        shutdown_requested = True
        # Optional: Unhook keys immediately? Let the listener loop handle it.

def keyboard_listener():
    """Runs in a separate thread to listen for keyboard hotkeys."""
    print("Keyboard listener thread started. F7: Clear History, F8: Pause/Resume, F9: Quit.")
    try:
        keyboard.add_hotkey('f7', handle_f7)
        keyboard.add_hotkey('f8', handle_f8)
        keyboard.add_hotkey('f9', handle_f9)

        # Keep the thread alive while checking for shutdown request
        while not shutdown_requested:
            time.sleep(0.1) # Check periodically

    except Exception as e:
        print(f"Error in keyboard listener thread: {e}")
    finally:
        print("Keyboard listener thread stopping and unhooking keys.")
        try:
            keyboard.unhook_all() # Clean up hooks
        except Exception as unhook_e:
            print(f"Error unhooking keyboard keys: {unhook_e}")
# --- End Keyboard Shortcut Handlers ---


# --- Chat Logging Function ---
def log_chat_interaction(user_name: str, user_message: str, bot_name: str, bot_message: str):
    """Logs the chat interaction to a date-stamped file if enabled."""
    if not config.ENABLE_CHAT_LOGGING:
        return

    try:
        # Ensure log directory exists
        log_dir = config.LOG_DIR
        os.makedirs(log_dir, exist_ok=True)

        # Get current date for filename
        today_date = datetime.date.today().strftime("%Y-%m-%d")
        log_file_path = os.path.join(log_dir, f"{today_date}.log")

        # Get current timestamp for log entry
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Format log entry
        log_entry = f"[{timestamp}] User ({user_name}): {user_message}\n"
        log_entry += f"[{timestamp}] Bot ({bot_name}): {bot_message}\n"
        log_entry += "---\n" # Separator

        # Append to log file
        with open(log_file_path, "a", encoding="utf-8") as f:
            f.write(log_entry)

    except Exception as e:
        print(f"Error writing to chat log: {e}")
# --- End Chat Logging Function ---


# --- Cleanup Function ---
async def shutdown():
    """Gracefully closes connections and stops monitoring task."""
    global wolfhart_persona_details, ui_monitor_task, shutdown_requested
    # Ensure shutdown is requested if called externally (e.g., Ctrl+C)
    if not shutdown_requested:
        print("Shutdown initiated externally (e.g., Ctrl+C).")
        shutdown_requested = True # Ensure listener thread stops

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
    # Removed print statement for active sessions


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
    global initialization_successful, main_task, loop, wolfhart_persona_details, trigger_queue, ui_monitor_task, shutdown_requested, script_paused, command_queue
    try:
        # 1. Load Persona Synchronously (before async loop starts)
        load_persona_from_file() # Corrected function

        # 2. Initialize MCP Connections Asynchronously
        await initialize_mcp_connections()

        # Warn if no servers connected successfully, but continue
        if not active_mcp_sessions:
             print("\n\033[93m[!]\033[0m Unable to connect to any MCP server, or no server is configured.")
             # Removed 'return' statement to allow continuation
        else:
             print(f"Successfully connected to {len(active_mcp_sessions)} MCP server(s): {list(active_mcp_sessions.keys())}")

        initialization_successful = True # Keep this, might be useful elsewhere

        # 3. Get loop and set it for keyboard handlers
        loop = asyncio.get_running_loop()
        set_main_loop_and_queue(loop, command_queue) # Pass loop and queue

        # 4. Start Keyboard Listener Thread
        print("\n--- Starting keyboard listener thread ---")
        kb_thread = threading.Thread(target=keyboard_listener, daemon=True) # Use daemon thread
        kb_thread.start()

        # 5. Start UI Monitoring in a separate thread
        print("\n--- Starting UI monitoring thread ---")
        # Use the new monitoring loop function, passing both queues
        monitor_task = loop.create_task(
            asyncio.to_thread(ui_interaction.run_ui_monitoring_loop, trigger_queue, command_queue), # Pass command_queue
            name="ui_monitor"
        )
        ui_monitor_task = monitor_task # Store task reference for shutdown

        # 6. Start the main processing loop (non-blocking check on queue)
        print("\n--- Wolfhart chatbot has started (waiting for triggers) ---")
        print(f"Available tools: {len(all_discovered_mcp_tools)}")
        if wolfhart_persona_details: print("Persona data loaded.")
        else: print("Warning: Failed to load Persona data.")
        print("F7: Clear History, F8: Pause/Resume, F9: Quit.")

        while True:
            # --- Check for Shutdown Request ---
            if shutdown_requested:
                print("Shutdown requested via F9. Exiting main loop.")
                break

            # --- Check for Pause State ---
            if script_paused:
                # Script is paused by F8, just sleep briefly
                await asyncio.sleep(0.1)
                continue # Skip the rest of the loop

            # --- Wait for Trigger Data (Blocking via executor) ---
            trigger_data = None
            try:
                # Use run_in_executor with the blocking get() method
                # This will efficiently wait until an item is available in the queue
                print("Waiting for UI trigger (from thread-safe Queue)...") # Log before blocking wait
                trigger_data = await loop.run_in_executor(None, trigger_queue.get)
            except Exception as e:
                # Handle potential errors during queue get (though less likely with blocking get)
                print(f"Error getting data from trigger_queue: {e}")
                await asyncio.sleep(0.5) # Wait a bit before retrying
                continue

            # --- Process Trigger Data (if received) ---
            # No need for 'if trigger_data:' check here, as get() blocks until data is available
            # --- Pause UI Monitoring (Only if not already paused by F8) ---
            if not script_paused:
                print("Pausing UI monitoring before LLM call...")
                # Corrected indentation below
                pause_command = {'action': 'pause'}
                try:
                    await loop.run_in_executor(None, command_queue.put, pause_command)
                    print("Pause command placed in queue.")
                except Exception as q_err:
                    print(f"Error putting pause command in queue: {q_err}")
            else: # Corrected indentation for else
                print("Script already paused by F8, skipping automatic pause.")
            # --- End Pause ---

            # Process trigger data (Corrected indentation for this block - unindented one level)
            sender_name = trigger_data.get('sender')
            bubble_text = trigger_data.get('text')
            bubble_region = trigger_data.get('bubble_region') # <-- Extract bubble_region
            bubble_snapshot = trigger_data.get('bubble_snapshot') # <-- Extract snapshot
            search_area = trigger_data.get('search_area') # <-- Extract search_area
            print(f"\n--- Received trigger from UI ---")
            print(f"   Sender: {sender_name}")
            print(f"   Content: {bubble_text[:100]}...")
            if bubble_region:
                print(f"   Bubble Region: {bubble_region}") # <-- Log bubble_region

            if not sender_name or not bubble_text: # bubble_region is optional context, don't fail if missing
                print("Warning: Received incomplete trigger data (missing sender or text), skipping.")
                # Resume UI if we paused it automatically
                if not script_paused:
                    print("Resuming UI monitoring after incomplete trigger.")
                    resume_command = {'action': 'resume'}
                    try:
                        await loop.run_in_executor(None, command_queue.put, resume_command)
                    except Exception as q_err:
                        print(f"Error putting resume command in queue: {q_err}")
                continue

            # --- Add user message to history ---
            timestamp = datetime.datetime.now() # Get current timestamp
            conversation_history.append((timestamp, 'user', sender_name, bubble_text))
            print(f"Added user message from {sender_name} to history at {timestamp}.")
            # --- End Add user message ---

            print(f"\n{config.PERSONA_NAME} is thinking...")
            try:
                # Get LLM response (現在返回的是一個字典)
                # --- Pass history and current sender name ---
                bot_response_data = await llm_interaction.get_llm_response(
                    current_sender_name=sender_name, # Pass current sender
                    history=list(conversation_history), # Pass a copy of the history
                    mcp_sessions=active_mcp_sessions,
                    available_mcp_tools=all_discovered_mcp_tools,
                    persona_details=wolfhart_persona_details
                )

                # 提取對話內容
                bot_dialogue = bot_response_data.get("dialogue", "")
                valid_response = bot_response_data.get("valid_response", False) # <-- 獲取 valid_response 標誌
                print(f"{config.PERSONA_NAME}'s dialogue response: {bot_dialogue}")
                # --- DEBUG PRINT ---
                print(f"DEBUG main.py: Before check - bot_dialogue='{bot_dialogue}', valid_response={valid_response}, dialogue_is_truthy={bool(bot_dialogue)}")
                # --- END DEBUG PRINT ---

                # 處理命令 (如果有的話)
                commands = bot_response_data.get("commands", [])
                if commands:
                    print(f"Processing {len(commands)} command(s)...")
                    for cmd in commands:
                        cmd_type = cmd.get("type", "")
                        cmd_params = cmd.get("parameters", {}) # Parameters might be empty for remove_position

# --- Command Processing ---
                        if cmd_type == "remove_position":
                            if bubble_region: # Check if we have the context
                                # Debug info - print what we have
                                print(f"Processing remove_position command with:")
                                print(f"  bubble_region: {bubble_region}")
                                print(f"  bubble_snapshot available: {'Yes' if bubble_snapshot is not None else 'No'}")
                                print(f"  search_area available: {'Yes' if search_area is not None else 'No'}")

                                # Check if we have snapshot and search_area as well
                                if bubble_snapshot and search_area:
                                    print("Sending 'remove_position' command to UI thread with snapshot and search area...")
                                    command_to_send = {
                                        'action': 'remove_position',
                                        'trigger_bubble_region': bubble_region, # Original region (might be outdated)
                                        'bubble_snapshot': bubble_snapshot,     # Snapshot for re-location
                                        'search_area': search_area              # Area to search in
                                    }
                                    try:
                                        await loop.run_in_executor(None, command_queue.put, command_to_send)
                                    except Exception as q_err:
                                        print(f"Error putting remove_position command in queue: {q_err}")
                                else:
                                    # If we have bubble_region but missing other parameters, use a dummy search area
                                    # and let UI thread take a new screenshot
                                    print("Missing bubble_snapshot or search_area, trying with defaults...")

                                    # Use the bubble_region itself as a fallback search area if needed
                                    default_search_area = None
                                    if search_area is None and bubble_region:
                                        # Convert bubble_region to a proper search area format if needed
                                        if len(bubble_region) == 4:
                                            default_search_area = bubble_region

                                    command_to_send = {
                                        'action': 'remove_position',
                                        'trigger_bubble_region': bubble_region,
                                        'bubble_snapshot': bubble_snapshot,     # Pass as is, might be None
                                        'search_area': default_search_area if search_area is None else search_area
                                    }

                                    try:
                                        await loop.run_in_executor(None, command_queue.put, command_to_send)
                                        print("Command sent with fallback parameters.")
                                    except Exception as q_err:
                                        print(f"Error putting remove_position command in queue: {q_err}")
                        else:
                            print("Error: Cannot process 'remove_position' command without bubble_region context.")
                        # Add other command handling here if needed
                        # elif cmd_type == "some_other_command":
                        #    # Handle other commands
                        #    pass
                        # elif cmd_type == "some_other_command":
                        #    # Handle other commands
                        #    pass
                        # else:
                        #     # 2025-04-19: Commented out - MCP tools like web_search are now handled
                        #     # internally by llm_interaction.py's tool calling loop.
                        #     # main.py only needs to handle UI-specific commands like remove_position.
                        #     print(f"Ignoring command type from LLM JSON (already handled internally): {cmd_type}, parameters: {cmd_params}")
                        # --- End Command Processing ---

                # 記錄思考過程 (如果有的話)
                thoughts = bot_response_data.get("thoughts", "")
                if thoughts:
                    print(f"AI Thoughts: {thoughts[:150]}..." if len(thoughts) > 150 else f"AI Thoughts: {thoughts}")

                # 只有當有效回應時才發送到遊戲 (via command queue)
                if bot_dialogue and valid_response:
                    # --- Add bot response to history ---
                    timestamp = datetime.datetime.now() # Get current timestamp
                    conversation_history.append((timestamp, 'bot', config.PERSONA_NAME, bot_dialogue))
                    print(f"Added bot response to history at {timestamp}.")
                    # --- End Add bot response ---

                    # --- Log the interaction ---
                    log_chat_interaction(
                        user_name=sender_name,
                        user_message=bubble_text,
                        bot_name=config.PERSONA_NAME,
                        bot_message=bot_dialogue
                    )
                    # --- End Log interaction ---

                    print("Sending 'send_reply' command to UI thread...")
                    command_to_send = {'action': 'send_reply', 'text': bot_dialogue}
                    try:
                        # Put command into the queue for the UI thread to handle
                        await loop.run_in_executor(None, command_queue.put, command_to_send)
                        print("Command placed in queue.")
                    except Exception as q_err:
                        print(f"Error putting command in queue: {q_err}")
                else:
                    print("Not sending response: Invalid or empty dialogue content.")
                    # --- Log failed interaction attempt (optional) ---
                    # log_chat_interaction(
                    #     user_name=sender_name,
                    #     user_message=bubble_text,
                    #     bot_name=config.PERSONA_NAME,
                    #     bot_message="<No valid response generated>"
                    # )
                    # --- End Log failed attempt ---

            except Exception as e:
                print(f"\nError processing trigger or sending response: {e}")
                import traceback
                traceback.print_exc()
            finally:
                # --- Resume UI Monitoring (Only if not paused by F8) ---
                if not script_paused:
                    print("Resuming UI monitoring after processing...")
                    resume_command = {'action': 'resume'}
                    try:
                        await loop.run_in_executor(None, command_queue.put, resume_command)
                        print("Resume command placed in queue.")
                    except Exception as q_err:
                        print(f"Error putting resume command in queue: {q_err}")
                else:
                     print("Script is paused by F8, skipping automatic resume.")
                # --- End Resume ---
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
         # Ensure shutdown_requested is set for the listener thread
         shutdown_requested = True
         # Give a moment for things to potentially clean up
         time.sleep(0.5)
    except Exception as e:
        # Catch top-level errors during asyncio.run itself
        print(f"Top-level error during asyncio.run execution: {e}")
    finally:
        print("Program exited.")

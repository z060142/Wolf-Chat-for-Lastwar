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
# Import RobustMessageDeduplication and StateResetDetector from ui_interaction
from ui_interaction import RobustMessageDeduplication, StateResetDetector 
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
import chroma_client
import subprocess # Import subprocess module
import signal
import platform
import atexit
import psutil  # For robust process management
# Import position tool server for MCP integration
import position_tool_server
import json  # For file communication with MCP server
import time   # For heartbeat timestamps
# Conditionally import Windows-specific modules
if platform.system() == "Windows":
    try:
        import win32api
        import win32con
    except ImportError:
        print("Warning: 'pywin32' not installed. MCP server subprocess termination on exit might not work reliably on Windows.")
        win32api = None
        win32con = None
else:
    win32api = None
    win32con = None


# --- Global Variables ---
active_mcp_sessions: dict[str, ClientSession] = {}
# Store Popen objects for managed MCP servers (CRITICAL: Now actively used for cleanup)
mcp_server_processes: dict[str, asyncio.subprocess.Process] = {}
# Track MCP process PIDs for forced cleanup
mcp_server_pids: dict[str, int] = {}
all_discovered_mcp_tools: list[dict] = []
exit_stack = AsyncExitStack()
# Stores loaded persona data (as a string for easy injection into prompt)
wolfhart_persona_details: str | None = None
# --- Conversation History ---
# Store tuples of (timestamp, speaker_type, speaker_name, message_content)
# speaker_type can be 'user' or 'bot'
conversation_history = collections.deque(maxlen=50) # Store last 50 messages (user+bot) with timestamps

# --- Position Removal Lock --- (DISABLED)
# Tracks position removal usage per conversation to prevent duplicate execution
# position_removal_used = False  # Reset when conversation context changes or clears
# --- Use standard thread-safe queues ---
trigger_queue: ThreadSafeQueue = ThreadSafeQueue() # UI Thread -> Main Loop
command_queue: ThreadSafeQueue = ThreadSafeQueue() # Main Loop -> UI Thread
# MCP position tool result queue
position_result_queue: ThreadSafeQueue = ThreadSafeQueue() # UI Thread -> MCP Tool
# --- End Change ---
ui_monitor_task: asyncio.Task | None = None # To track the UI monitor task

# --- Keyboard Shortcut State ---
script_paused = False
shutdown_requested = False
main_loop = None # To store the main event loop for threadsafe calls
# --- End Keyboard Shortcut State ---

# --- Chat Context Management Functions ---
def save_chat_context(bubble_region, bubble_snapshot, search_area):
    """
    保存聊天上下文數據到文件，供MCP工具使用
    注意：不保存實際的bubble_snapshot數據，直接從全域變數讀取
    """
    try:
        context_data = {
            "timestamp": time.time(),
            "bubble_region": bubble_region,
            "search_area": search_area,
            "status": "active",
            "note": "bubble_snapshot_from_globals"  # 提示數據來源
        }
        
        with open(CHAT_CONTEXT_FILE, 'w', encoding='utf-8') as f:
            json.dump(context_data, f, ensure_ascii=False)
        
        print(f"Chat Context: Saved to {CHAT_CONTEXT_FILE}")
    except Exception as e:
        print(f"Error saving chat context: {e}")

def load_chat_context():
    """
    讀取聊天上下文數據，供MCP工具使用
    返回: (bubble_region, has_snapshot, search_area, age_seconds) 或 None
    """
    try:
        if not os.path.exists(CHAT_CONTEXT_FILE):
            return None
        
        with open(CHAT_CONTEXT_FILE, 'r', encoding='utf-8') as f:
            context_data = json.load(f)
        
        # 檢查數據時效性（5分鐘內）
        age_seconds = time.time() - context_data.get("timestamp", 0)
        if age_seconds > 300:  # 5分鐘
            print(f"Chat Context: Data too old ({age_seconds:.1f}s), ignoring")
            return None
        
        bubble_region = context_data.get("bubble_region")
        search_area = context_data.get("search_area")
        
        print(f"Chat Context: Loaded data from {age_seconds:.1f}s ago (snapshot from globals)")
        return bubble_region, search_area, age_seconds
    
    except Exception as e:
        print(f"Error loading chat context: {e}")
        return None
# --- End Chat Context Management ---

# --- MCP File Communication Constants ---
COMMAND_FILE = "position_command.json"
RESULT_FILE = "position_result.json" 
HEARTBEAT_FILE = "main_heartbeat.json"
CHAT_CONTEXT_FILE = "chat_context.json"  # 聊天上下文狀態文件
# --- End MCP File Communication ---


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
            print("\n--- F8 pressed: Resuming script and UI monitoring ---")
            resume_command = {'action': 'resume'}
            try:
                # Add a small delay? Let's try without first.
                # time.sleep(0.05) # Short delay between commands if needed
                main_loop.call_soon_threadsafe(command_queue.put_nowait, resume_command)
            except Exception as e:
                 print(f"Error sending resume command (F8): {e}")

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
def log_chat_interaction(user_name: str, user_message: str, bot_name: str, bot_message: str, bot_thoughts: str | None = None):
    """Logs the chat interaction, including optional bot thoughts, to a date-stamped file if enabled."""
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
        # Include thoughts if available
        if bot_thoughts:
            log_entry += f"[{timestamp}] Bot ({bot_name}) Thoughts: {bot_thoughts}\n"
        log_entry += f"[{timestamp}] Bot ({bot_name}) Dialogue: {bot_message}\n" # Label dialogue explicitly
        log_entry += "---\n" # Separator

        # Append to log file
        with open(log_file_path, "a", encoding="utf-8") as f:
            f.write(log_entry)

    except Exception as e:
        print(f"Error writing to chat log: {e}")
# --- End Chat Logging Function ---


# --- MCP Server Subprocess Termination Logic (ENHANCED for forced cleanup) ---
def terminate_all_mcp_servers():
    """
    CRITICAL: Force terminate all MCP server processes and their children.
    This function is called from multiple cleanup handlers to ensure no orphan processes.
    """
    global mcp_server_pids

    if not mcp_server_pids:
        print("[MCP-CLEANUP] No tracked MCP processes to terminate.")
        return

    print(f"[MCP-CLEANUP] Force terminating {len(mcp_server_pids)} MCP server process(es)...")

    for key, pid in list(mcp_server_pids.items()):
        try:
            # Use psutil for robust process handling
            parent_proc = psutil.Process(pid)
            print(f"[MCP-CLEANUP] Terminating '{key}' (PID: {pid})...")

            # Get all child processes BEFORE terminating parent
            try:
                children = parent_proc.children(recursive=True)
                print(f"[MCP-CLEANUP] Found {len(children)} child process(es) for '{key}'")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                children = []

            # Terminate parent first
            try:
                parent_proc.terminate()
                parent_proc.wait(timeout=3)
                print(f"[MCP-CLEANUP] '{key}' terminated gracefully.")
            except psutil.TimeoutExpired:
                print(f"[MCP-CLEANUP] '{key}' did not terminate, killing...")
                parent_proc.kill()
                parent_proc.wait(timeout=2)
                print(f"[MCP-CLEANUP] '{key}' killed.")
            except psutil.NoSuchProcess:
                print(f"[MCP-CLEANUP] '{key}' process already gone.")

            # Terminate all children
            for child in children:
                try:
                    if child.is_running():
                        print(f"[MCP-CLEANUP] Killing child PID: {child.pid}")
                        child.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

        except psutil.NoSuchProcess:
            print(f"[MCP-CLEANUP] '{key}' (PID: {pid}) not found.")
        except psutil.AccessDenied:
            print(f"[MCP-CLEANUP] Access denied for '{key}' (PID: {pid}).")
        except Exception as e:
            print(f"[MCP-CLEANUP] Error terminating '{key}' (PID: {pid}): {e}")

    # Clear tracking
    mcp_server_pids.clear()
    print("[MCP-CLEANUP] Finished MCP server cleanup.")

def windows_ctrl_handler(ctrl_type):
    """Handles Windows console control events."""
    if win32con and ctrl_type in (
        win32con.CTRL_C_EVENT,
        win32con.CTRL_BREAK_EVENT,
        win32con.CTRL_CLOSE_EVENT,
        win32con.CTRL_LOGOFF_EVENT,
        win32con.CTRL_SHUTDOWN_EVENT
    ):
        print(f"[INFO] Windows Control Event ({ctrl_type}) detected. Initiating MCP server termination.")
        # Directly call the termination function.
        # Avoid doing complex async operations here if possible.
        # The main shutdown sequence will handle async cleanup.
        terminate_all_mcp_servers()
        # Returning True indicates we handled the event,
        # but might prevent default clean exit. Let's return False
        # to allow Python's default handler to also run (e.g., for KeyboardInterrupt).
        return False # Allow other handlers to process the event
    return False # Event not handled

# Register the handler only on Windows and if imports succeeded
if platform.system() == "Windows" and win32api and win32con:
    try:
        win32api.SetConsoleCtrlHandler(windows_ctrl_handler, True)
        print("[INFO] Registered Windows console control handler for MCP server cleanup.")
    except Exception as e:
        print(f"[ERROR] Failed to register Windows console control handler: {e}")
# --- End MCP Server Termination Logic ---


# --- Cleanup Function ---
# --- MCP Position Tool Integration ---
async def execute_position_removal_with_feedback(action_type: str, user_context: str = "") -> dict:
    """
    為MCP tool提供的回調函數，執行職位移除並返回結果
    
    Args:
        action_type: 操作類型，應為 "remove_position_with_feedback"
        user_context: 用戶上下文信息
    
    Returns:
        執行結果字典
    """
    print(f"MCP Callback: Received request for {action_type} with context: {user_context}")
    
    if action_type == "remove_position_with_feedback":
        # 檢查是否有必要的全域變數（現有的bubble相關數據）
        # 這些變數在main loop中會被設定
        if 'bubble_region' in globals() and bubble_region:
            print(f"MCP Callback: Using bubble_region: {bubble_region}")
            
            # 構造命令，重用現有的UI操作邏輯
            command_to_send = {
                'action': 'remove_position_with_feedback',  # 新的action type
                'trigger_bubble_region': bubble_region,
                'bubble_snapshot': bubble_snapshot if 'bubble_snapshot' in globals() else None,
                'search_area': search_area if 'search_area' in globals() else None,
                'user_context': user_context,
                'mcp_request': True  # 標記這是來自MCP的請求
            }
            
            print("MCP Callback: Sending command to UI thread...")
            # 使用現有的command_queue機制
            try:
                await asyncio.get_event_loop().run_in_executor(None, command_queue.put, command_to_send)
                print("MCP Callback: Command sent to UI thread, waiting for result...")
                
                # 等待UI處理結果
                result = await wait_for_ui_result(timeout=15)  # 給UI操作更長的超時時間
                print(f"MCP Callback: Received result: {result}")
                return result
                
            except Exception as e:
                error_result = {
                    "status": "error",
                    "message": f"發送命令到UI線程失敗: {str(e)}",
                    "user_context": user_context,
                    "execution_time": datetime.datetime.now().isoformat()
                }
                print(f"MCP Callback Error: {error_result}")
                return error_result
        else:
            error_result = {
                "status": "error", 
                "message": "無法獲取用戶聊天區域信息，請確保在聊天觸發後使用此功能",
                "user_context": user_context,
                "execution_time": datetime.datetime.now().isoformat()
            }
            print(f"MCP Callback: No bubble_region available: {error_result}")
            return error_result
    else:
        error_result = {
            "status": "error",
            "message": f"不支援的操作類型: {action_type}",
            "user_context": user_context,
            "execution_time": datetime.datetime.now().isoformat()
        }
        print(f"MCP Callback: Unsupported action type: {error_result}")
        return error_result

async def wait_for_ui_result(timeout: float = 10.0) -> dict:
    """
    等待UI線程返回的結果
    
    Args:
        timeout: 超時時間（秒）
    
    Returns:
        UI操作結果字典
    """
    start_time = asyncio.get_event_loop().time()
    
    while True:
        current_time = asyncio.get_event_loop().time()
        if current_time - start_time > timeout:
            return {
                "status": "error",
                "message": f"UI操作超時（{timeout}秒），可能是UI識別失敗",
                "execution_time": datetime.datetime.now().isoformat()
            }
        
        try:
            # 非阻塞式檢查result queue
            result = await asyncio.get_event_loop().run_in_executor(
                None, position_result_queue.get, False  # False = non-blocking
            )
            return result
        except QueueEmpty:
            # 沒有結果，短暫等待後重試
            await asyncio.sleep(0.1)
        except Exception as e:
            return {
                "status": "error",
                "message": f"等待UI結果時發生錯誤: {str(e)}",
                "execution_time": datetime.datetime.now().isoformat()
            }

# --- End MCP Position Tool Integration ---

# --- MCP File Communication Functions ---
async def monitor_mcp_commands():
    """監控MCP命令文件並處理跨進程通訊"""
    print("MCP File Monitor: Starting command file monitoring...")
    
    while not shutdown_requested:
        try:
            # 更新心跳文件
            try:
                heartbeat_data = {
                    "timestamp": time.time(),
                    "status": "running",
                    "script_paused": script_paused
                }
                with open(HEARTBEAT_FILE, 'w', encoding='utf-8') as f:
                    json.dump(heartbeat_data, f, ensure_ascii=False)
            except Exception as hb_error:
                print(f"MCP Monitor: Error updating heartbeat: {hb_error}")
            
            # 檢查命令文件
            if os.path.exists(COMMAND_FILE):
                try:
                    with open(COMMAND_FILE, 'r', encoding='utf-8') as f:
                        command = json.load(f)
                    
                    print(f"MCP Monitor: Received command: {command}")
                    
                    # 處理命令
                    await process_mcp_command(command)
                    
                    # 清理命令文件
                    try:
                        os.remove(COMMAND_FILE)
                        print("MCP Monitor: Command file cleaned")
                    except:
                        print("MCP Monitor: Warning - Could not remove command file")
                        
                except json.JSONDecodeError as json_err:
                    print(f"MCP Monitor: Invalid JSON in command file: {json_err}")
                    try:
                        os.remove(COMMAND_FILE)  # 清理無效文件
                    except:
                        pass
                except Exception as cmd_error:
                    print(f"MCP Monitor: Error processing command file: {cmd_error}")
                
        except Exception as monitor_error:
            print(f"MCP Monitor: Unexpected error in monitoring loop: {monitor_error}")
        
        await asyncio.sleep(0.5)  # 500ms檢查一次
    
    print("MCP File Monitor: Shutdown requested, stopping command monitoring")

async def process_mcp_command(command):
    """處理來自MCP server的命令"""
    action = command.get("action")
    request_id = command.get("request_id")
    attempt = command.get("attempt", 1)
    
    print(f"MCP Processor: Processing action '{action}' for request {request_id} (attempt {attempt})")
    
    if action == "remove_position_with_feedback":
        # 優先從聊天上下文文件讀取數據，如果沒有則使用全域變數
        context_data = load_chat_context()
        bubble_region_to_use = None
        search_area_to_use = None
        has_snapshot = False
        data_source = "none"
        
        if context_data:
            bubble_region_to_use, search_area_to_use, age = context_data
            data_source = f"context_file_({age:.1f}s_old)"
            print(f"MCP Processor: Using chat context data ({age:.1f}s old)")
            print(f"MCP Processor: Bubble region from context: {bubble_region_to_use}")
        elif 'bubble_region' in globals() and bubble_region is not None:
            # Fallback：使用全域變數
            bubble_region_to_use = bubble_region
            search_area_to_use = search_area if 'search_area' in globals() else None
            data_source = "global_variables"
            print(f"MCP Processor: Using global variables as fallback")
            print(f"MCP Processor: Bubble region from globals: {bubble_region_to_use}")
        
        if bubble_region_to_use:
            
            print(f"MCP Processor: Proceeding with data from {data_source}")
            
            # 優先使用全域變數中的原始 bubble_snapshot（不論數據來源）
            original_snapshot = None
            if 'bubble_snapshot' in globals() and bubble_snapshot is not None:
                original_snapshot = bubble_snapshot
                print(f"MCP Processor: Found original bubble_snapshot in globals")
            else:
                print(f"MCP Processor: No original bubble_snapshot available in globals")
            
            try:
                # 構造UI命令，使用原始的bubble_snapshot
                command_to_send = {
                    'action': 'remove_position_with_feedback',
                    'trigger_bubble_region': bubble_region_to_use,
                    'bubble_snapshot': original_snapshot,  # 直接使用全域變數中的原始數據
                    'search_area': search_area_to_use,
                    'mcp_request': True,
                    'request_id': request_id,
                    'data_source': data_source,  # 記錄數據來源
                    'has_original_snapshot': original_snapshot is not None
                }
                
                print("MCP Processor: Sending command to UI thread...")
                await asyncio.get_event_loop().run_in_executor(None, command_queue.put, command_to_send)
                
                # 等待UI處理完成（UI thread會直接寫入result文件）
                print("MCP Processor: Command sent to UI thread, UI will handle result file creation")
                
            except Exception as ui_error:
                print(f"MCP Processor: Error sending to UI thread: {ui_error}")
                
                error_result = {
                    "status": "error",
                    "message": f"無法發送命令到UI線程: {str(ui_error)}",
                    "request_id": request_id,
                    "execution_time": datetime.datetime.now().isoformat()
                }
                
                await write_result_file(error_result)
        else:
            print("MCP Processor: No bubble region available from any source")
            
            # 檢查是否有全域 bubble_snapshot 但缺少 bubble_region
            has_global_snapshot = 'bubble_snapshot' in globals() and bubble_snapshot is not None
            
            if has_global_snapshot:
                error_message = "有截圖數據但缺少泡泡位置信息，請在新的聊天觸發後再嘗試"
                suggestion = "請等待新的聊天消息觸發，系統將重新獲取完整的上下文數據"
            else:
                error_message = "無法獲取聊天區域信息和截圖數據，請在聊天觸發後使用此功能"
                suggestion = "請等待遊戲中有人發言，系統會自動捕獲聊天上下文數據"
            
            error_result = {
                "status": "error",
                "message": error_message,
                "suggestion": suggestion,
                "request_id": request_id,
                "debug_info": {
                    "has_global_snapshot": has_global_snapshot,
                    "checked_sources": ["chat_context_file", "global_variables"]
                },
                "execution_time": datetime.datetime.now().isoformat(),
                "suggestion": "請確保在遊戲聊天觸發後再嘗試移除職位"
            }
            
            await write_result_file(error_result)
    else:
        print(f"MCP Processor: Unknown action: {action}")
        
        error_result = {
            "status": "error",
            "message": f"不支援的操作類型: {action}",
            "request_id": request_id,
            "execution_time": datetime.datetime.now().isoformat()
        }
        
        await write_result_file(error_result)

async def write_result_file(result):
    """寫入結果文件"""
    try:
        with open(RESULT_FILE, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"MCP Processor: Result written for request {result.get('request_id')}: {result.get('status')}")
    except Exception as write_error:
        print(f"MCP Processor: Error writing result file: {write_error}")

# --- End MCP File Communication Functions ---

async def shutdown():
    """Gracefully closes connections and stops monitoring tasks/processes."""
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
    # This will trigger the __aexit__ method of stdio_client contexts,
    # which we assume handles terminating the server subprocesses it started.
    print(f"Closing MCP Server connections (via AsyncExitStack)...")
    try:
        # This will close the ClientSession contexts, which might involve
        # closing the stdin/stdout pipes to the (now hopefully terminated) servers.
        await exit_stack.aclose()
        print("AsyncExitStack closed successfully.")
    except Exception as e:
        print(f"Error closing AsyncExitStack: {e}")
        import traceback
        traceback.print_exc()

    # 3. CRITICAL: Force terminate all MCP servers (safety net)
    print("[SHUTDOWN] Force terminating MCP servers as safety net...")
    terminate_all_mcp_servers()

    # 4. Clean up MCP communication files
    try:
        for file_path in [COMMAND_FILE, RESULT_FILE, HEARTBEAT_FILE, CHAT_CONTEXT_FILE]:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"Cleaned up MCP file: {file_path}")
    except Exception as cleanup_error:
        print(f"Warning: Error cleaning MCP files: {cleanup_error}")

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
    global all_discovered_mcp_tools, active_mcp_sessions, exit_stack, mcp_server_pids
    print(f"\nProcessing Server: '{key}'")
    command = server_config.get("command")
    args = server_config.get("args", [])
    process_env = os.environ.copy()
    if server_config.get("env") and isinstance(server_config["env"], dict):
        process_env.update(server_config["env"])

    if not command:
        print(f"==> Error: Missing 'command' in Server '{key}' configuration. <==")
        return

    # Use StdioServerParameters again
    server_params = StdioServerParameters(
        command=command, args=args, env=process_env,
        # Note: We assume stdio_client handles necessary flags internally or
        # that its cleanup mechanism is sufficient. Explicit flag passing here
        # might require checking the mcp library's StdioServerParameters definition.
    )

    try:
        # --- Use stdio_client again ---
        print(f"Using stdio_client to start and connect to Server '{key}'...")
        # Pass server_params to stdio_client
        # stdio_client manages the subprocess lifecycle within its context
        read, write = await exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        print(f"stdio_client for '{key}' active, provides read/write streams.")

        # --- CRITICAL: Track MCP process PID for forced cleanup ---
        await asyncio.sleep(0.1)  # Brief delay to ensure process is created
        try:
            # Find the newly created process by command line
            target_cmdline_parts = [command] + args
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
                try:
                    cmdline = proc.cmdline()
                    # Match command and first unique arg
                    if cmdline and len(cmdline) >= len(args) + 1:
                        if command.lower() in cmdline[0].lower():
                            # Check if args match
                            matches_args = any(arg in ' '.join(cmdline) for arg in args if arg)
                            if matches_args or len(args) == 0:
                                mcp_server_pids[key] = proc.pid
                                print(f"[MCP-TRACK] Registered '{key}' server PID: {proc.pid}")
                                break
                except (psutil.NoSuchProcess, psutil.AccessDenied, IndexError):
                    continue
        except Exception as track_err:
            print(f"[MCP-TRACK] Warning: Failed to track PID for '{key}': {track_err}")
        # --- End PID tracking ---
        # --- End stdio_client usage ---

        # stdio_client provides the correct stream types for ClientSession
        session = await exit_stack.enter_async_context(
            ClientSession(read, write)
        )
        print(f"ClientSession for '{key}' context entered.")

        # We no longer manually manage the process object here.
        # We rely on stdio_client's context manager (__aexit__) to terminate the process.

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
        if getattr(config, 'MCP_SERVERS_ENABLED', {}).get(key, server_config.get("enabled", True))  # Check both sources for enabled state
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

# --- Memory System Initialization ---
def initialize_memory_system():
    """Initialize memory system"""
    if hasattr(config, 'ENABLE_PRELOAD_PROFILES') and config.ENABLE_PRELOAD_PROFILES:
        print("\nInitializing ChromaDB memory system...")
        if chroma_client.initialize_chroma_client():
            # Check if collections are available
            collections_to_check = [
                config.PROFILES_COLLECTION,
                config.CONVERSATIONS_COLLECTION,
                config.BOT_MEMORY_COLLECTION
            ]
            success_count = 0
            for coll_name in collections_to_check:
                if chroma_client.get_collection(coll_name):
                    success_count += 1

            print(f"Memory system initialization complete, successfully connected to {success_count}/{len(collections_to_check)} collections")
            return True
        else:
            print("Memory system initialization failed, falling back to tool calls")
            return False
    else:
        print("Memory system preloading is disabled, will use tool calls to get memory")
        return False
# --- End Memory System Initialization ---

# --- Main Async Function ---
async def run_main_with_exit_stack():
    """Initializes connections, loads persona, starts UI monitor and main processing loop."""
    global initialization_successful, main_task, loop, wolfhart_persona_details, trigger_queue, ui_monitor_task, shutdown_requested, script_paused, command_queue
    try:
        # 1. Load Persona Synchronously (before async loop starts)
        load_persona_from_file() # Corrected function

        # 2. Initialize Memory System (after loading config, before main loop)
        memory_system_active = initialize_memory_system()

        # 3. Initialize MCP Connections Asynchronously
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
        
        # 5c. Initialize Robust Deduplication System
        def initialize_robust_deduplication():
            """初始化強化版去重系統"""
            deduplicator_instance = RobustMessageDeduplication(
                storage_file="wolf_chat_dedup.json"
                # max_messages 使用預設值（統一的 DEDUPLICATION_WINDOW_SIZE）
            )
            state_monitor_instance = StateResetDetector("wolf_chat_state_resets.log")
            return deduplicator_instance, state_monitor_instance

        deduplicator, state_monitor = initialize_robust_deduplication()

        # Use the new monitoring loop function, passing trigger_queue, command_queue, deduplicator, and state_monitor
        monitor_task = loop.create_task(
            asyncio.to_thread(ui_interaction.run_ui_monitoring_loop_enhanced, trigger_queue, command_queue, deduplicator, state_monitor),
            name="ui_monitor_enhanced"
        )
        ui_monitor_task = monitor_task # Store task reference for shutdown
        # Note: UI task cancellation is handled in shutdown()

        # 5b. Game Window Monitoring is now handled by Setup.py

        # 5d. Start Periodic Cleanup and Stats Logging Timer for Deduplicator
        def periodic_robust_cleanup_and_stats():
            if not shutdown_requested: # Only run if not shutting down
                print("Main Thread: Running periodic robust deduplicator cleanup and stats logging...")
                deduplicator._save_to_storage(force=True) # Force save current state
                stats = deduplicator.get_stats()
                print(f"Main Thread - Dedup Stats: {stats['active_records']} active records (total: {stats['total_records']})")
                # Reschedule the timer
                cleanup_timer = threading.Timer(600, periodic_robust_cleanup_and_stats) # 10 minutes
                cleanup_timer.daemon = True
                cleanup_timer.start()
            else:
                print("Main Thread: Shutdown requested, not rescheduling robust deduplicator cleanup.")

        print("\n--- Starting periodic robust deduplicator cleanup and stats timer (10 min interval) ---")
        initial_cleanup_timer = threading.Timer(600, periodic_robust_cleanup_and_stats)
        initial_cleanup_timer.daemon = True
        initial_cleanup_timer.start()
        # Note: This timer will run in a separate thread.
        # Ensure it's handled correctly on shutdown if it holds resources.
        # Since it's a daemon thread and reschedules itself, it should exit when the main program exits.

        # 6. Start the main processing loop (non-blocking check on queue)
        print("\n--- Wolfhart chatbot has started (waiting for triggers) ---")
        print(f"Available tools: {len(all_discovered_mcp_tools)}")
        if wolfhart_persona_details: print("Persona data loaded.")
        else: print("Warning: Failed to load Persona data.")
        
        # 啟動MCP文件通訊監控（替代舊的回調機制）
        try:
            monitor_task = asyncio.create_task(monitor_mcp_commands())
            print("MCP File Communication monitor started successfully.")
        except Exception as e:
            print(f"Warning: Failed to start MCP file communication monitor: {e}")
            monitor_task = None
        
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
            
            # 保存聊天上下文數據供MCP工具使用
            if bubble_region:
                save_chat_context(bubble_region, bubble_snapshot, search_area)
            
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

            # --- Memory Preloading ---
            user_profile = None
            related_memories = []
            bot_knowledge = []
            memory_retrieval_time = 0

            # If memory system is active and preloading is enabled
            if memory_system_active and hasattr(config, 'ENABLE_PRELOAD_PROFILES') and config.ENABLE_PRELOAD_PROFILES:
                try:
                    memory_start_time = time.time()

                    # 1. Get user profile
                    user_profile = chroma_client.get_entity_profile(sender_name)

                    # 2. Preload related memories if configured
                    if hasattr(config, 'PRELOAD_RELATED_MEMORIES') and config.PRELOAD_RELATED_MEMORIES > 0:
                        related_memories = chroma_client.get_related_memories(
                            sender_name,
                            limit=config.PRELOAD_RELATED_MEMORIES
                        )

                    # 3. Optionally preload bot knowledge based on message content
                    key_game_terms = ["capital_position", "capital_administrator_role", "server_hierarchy",
                                     "last_war", "winter_war", "excavations", "blueprints",
                                     "honor_points", "golden_eggs", "diamonds"]

                    # Check if message contains these keywords
                    found_terms = [term for term in key_game_terms if term.lower() in bubble_text.lower()]

                    if found_terms:
                        # Retrieve knowledge for found terms (limit to 2 terms, 2 results each)
                        for term in found_terms[:2]:
                            term_knowledge = chroma_client.get_bot_knowledge(term, limit=2)
                            bot_knowledge.extend(term_knowledge)

                    memory_retrieval_time = time.time() - memory_start_time
                    print(f"Memory retrieval complete: User profile {'successful' if user_profile else 'failed'}, "
                          f"{len(related_memories)} related memories, "
                          f"{len(bot_knowledge)} bot knowledge, "
                          f"total time {memory_retrieval_time:.3f}s")

                except Exception as mem_err:
                    print(f"Error during memory retrieval: {mem_err}")
                    # Clear all memory data on error to avoid using partial data
                    user_profile = None
                    related_memories = []
                    bot_knowledge = []
            # --- End Memory Preloading ---

            print(f"\n{config.PERSONA_NAME} is thinking...")
            try:
                # 準備 UI 上下文數據（bubble_snapshot 等）
                ui_context = {
                    'bubble_snapshot': bubble_snapshot,
                    'bubble_region': bubble_region,
                    'search_area': search_area
                }
                print(f"Main: Prepared UI context - snapshot: {bubble_snapshot is not None}, region: {bubble_region}, search_area: {search_area is not None}")
                
                # Get LLM response, passing preloaded memory data and UI context
                bot_response_data = await llm_interaction.get_llm_response(
                    current_sender_name=sender_name,
                    history=list(conversation_history),
                    mcp_sessions=active_mcp_sessions,
                    available_mcp_tools=all_discovered_mcp_tools,
                    persona_details=wolfhart_persona_details,
                    user_profile=user_profile,                # Added: Pass user profile
                    related_memories=related_memories,        # Added: Pass related memories
                    bot_knowledge=bot_knowledge,              # Added: Pass bot knowledge
                    ui_context=ui_context                     # Added: Pass UI context
                )

                # Extract dialogue content
                bot_dialogue = bot_response_data.get("dialogue", "")
                valid_response = bot_response_data.get("valid_response", False) # <-- Get valid_response flag
                print(f"{config.PERSONA_NAME}'s dialogue response: {bot_dialogue}")
                # --- DEBUG PRINT ---
                print(f"DEBUG main.py: Before check - bot_dialogue='{bot_dialogue}', valid_response={valid_response}, dialogue_is_truthy={bool(bot_dialogue)}")
                # --- END DEBUG PRINT ---

                # Process commands (if any)
                commands = bot_response_data.get("commands", [])
                if commands:
                    print(f"Processing {len(commands)} command(s)...")
                    for cmd in commands:
                        cmd_type = cmd.get("type", "")
                        cmd_params = cmd.get("parameters", {}) # Parameters might be empty for remove_position

# --- Command Processing ---
                        # DEPRECATED: Legacy command method - use MCP remove_user_position() tool instead
                        if cmd_type == "remove_position":  # Legacy method
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
                            print("Error: Cannot process 'remove_position' command without bubble_region context. Consider using MCP remove_user_position() tool instead.")
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
                        #     # main.py handles MCP file communication for remove_position_with_feedback via MCP tools.
                        #     print(f"Ignoring command type from LLM JSON (already handled internally): {cmd_type}, parameters: {cmd_params}")
                        # --- End Command Processing ---

                # Log thoughts (if any)
                thoughts = bot_response_data.get("thoughts", "")
                if thoughts:
                    print(f"AI Thoughts: {thoughts[:150]}..." if len(thoughts) > 150 else f"AI Thoughts: {thoughts}")

                # Only send to game when valid response (via command queue)
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
                        bot_message=bot_dialogue,
                        bot_thoughts=thoughts # Pass the extracted thoughts
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

# --- Function to set DPI Awareness ---
def set_dpi_awareness():
    """Attempts to set the process DPI awareness for better scaling handling on Windows."""
    try:
        import ctypes
        # DPI Awareness constants (Windows 10, version 1607 and later)
        # DPI_AWARENESS_CONTEXT_UNAWARE = -1
        DPI_AWARENESS_CONTEXT_SYSTEM_AWARE = -2
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE = -3
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4

        # Try setting System Aware first
        result = ctypes.windll.shcore.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_SYSTEM_AWARE)
        if result == 0: # S_OK or E_ACCESSDENIED if already set
             print("Process DPI awareness set to System Aware (or already set).")
             return True
        else:
             # Try getting last error if needed: ctypes.get_last_error()
             print(f"Warning: Failed to set DPI awareness (SetProcessDpiAwarenessContext returned {result}). Window scaling might be incorrect.")
             return False
    except ImportError:
        print("Warning: 'ctypes' module not found. Cannot set DPI awareness.")
        return False
    except AttributeError:
        print("Warning: SetProcessDpiAwarenessContext not found (likely older Windows version or missing shcore.dll). Cannot set DPI awareness.")
        return False
    except Exception as e:
        print(f"Warning: An unexpected error occurred while setting DPI awareness: {e}")
        return False

# --- Multi-Layer Cleanup Handlers ---
def emergency_cleanup_handler(signum=None, frame=None):
    """
    CRITICAL: Emergency cleanup handler for forced termination.
    Called from multiple sources: atexit, signal handlers, Windows console handler.
    """
    print(f"\n[EMERGENCY-CLEANUP] Triggered (signal: {signum})")

    # Force terminate all MCP servers
    terminate_all_mcp_servers()

    # Clean up MCP communication files
    try:
        for file_path in [COMMAND_FILE, RESULT_FILE, HEARTBEAT_FILE, CHAT_CONTEXT_FILE]:
            if os.path.exists(file_path):
                os.remove(file_path)
    except Exception as e:
        print(f"[EMERGENCY-CLEANUP] Error removing files: {e}")

    print("[EMERGENCY-CLEANUP] Completed.")

def setup_cleanup_handlers():
    """Register cleanup handlers at multiple levels for maximum reliability."""

    # 1. atexit handler (normal Python exit)
    atexit.register(emergency_cleanup_handler)
    print("[CLEANUP-INIT] Registered atexit handler")

    # 2. Signal handlers (SIGTERM, SIGINT)
    try:
        signal.signal(signal.SIGTERM, emergency_cleanup_handler)
        signal.signal(signal.SIGINT, emergency_cleanup_handler)
        print("[CLEANUP-INIT] Registered SIGTERM and SIGINT handlers")
    except Exception as e:
        print(f"[CLEANUP-INIT] Warning: Failed to register signal handlers: {e}")

    # 3. Windows console handler (already registered in windows_ctrl_handler)
    # See lines 309-318 for existing Windows handler setup

# --- Program Entry Point ---
if __name__ == "__main__":
    print("Program starting...")

    # --- Set DPI Awareness early ---
    set_dpi_awareness()
    # --- End DPI Awareness setting ---

    # --- Setup Multi-Layer Cleanup Handlers ---
    setup_cleanup_handlers()
    print("[INIT] Multi-layer cleanup handlers registered")
    # --- End Cleanup Handlers Setup ---

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
        # Final safety net - ensure MCP cleanup
        emergency_cleanup_handler()
        print("Program exited.")

#!/usr/bin/env python
"""
Game Window Monitor Module

Continuously monitors the game window specified in the config,
ensuring it stays at the configured position, size, and remains topmost.
"""

import time
import datetime # Added
import subprocess # Added
import psutil # Added
import sys # Added
import json # Added
import os # Added for basename
import pygetwindow as gw
import win32gui
import win32con
import config
import logging
# import multiprocessing # Keep for Pipe/Queue if needed later, though using stdio now
# NOTE: config.py should handle dotenv loading. This script only imports values.

# --- Setup Logging ---
monitor_logger = logging.getLogger('GameMonitor')
# Basic config for direct run, main.py might configure differently
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- Helper Functions ---

def restart_game_process():
    """Finds and terminates the existing game process, then restarts it."""
    monitor_logger.info("嘗試重啟遊戲進程。(Attempting to restart game process.)")
    game_path = config.GAME_EXECUTABLE_PATH
    if not game_path or not os.path.exists(os.path.dirname(game_path)): # Basic check
         monitor_logger.error(f"遊戲執行檔路徑 '{game_path}' 無效或目錄不存在，無法重啟。(Game executable path '{game_path}' is invalid or directory does not exist, cannot restart.)")
         return

    target_process_name = "LastWar.exe" # Correct process name
    launcher_path = config.GAME_EXECUTABLE_PATH # Keep launcher path for restarting
    monitor_logger.info(f"尋找名稱為 '{target_process_name}' 的遊戲進程。(Looking for game process named '{target_process_name}')")

    terminated = False
    process_found = False
    for proc in psutil.process_iter(['pid', 'name', 'exe']):
        try:
            proc_info = proc.info
            proc_name = proc_info.get('name')

            if proc_name == target_process_name:
                process_found = True
                monitor_logger.info(f"找到遊戲進程 PID: {proc_info['pid']}，名稱: {proc_name}。正在終止...(Found game process PID: {proc_info['pid']}, Name: {proc_name}. Terminating...)")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                    monitor_logger.info(f"進程 {proc_info['pid']} 已成功終止 (terminate)。(Process {proc_info['pid']} terminated successfully (terminate).)")
                    terminated = True
                except psutil.TimeoutExpired:
                    monitor_logger.warning(f"進程 {proc_info['pid']} 未能在 5 秒內終止 (terminate)，嘗試強制結束 (kill)。(Process {proc_info['pid']} did not terminate in 5s (terminate), attempting kill.)")
                    proc.kill()
                    proc.wait(timeout=5) # Wait for kill with timeout
                    monitor_logger.info(f"進程 {proc_info['pid']} 已強制結束 (kill)。(Process {proc_info['pid']} killed.)")
                    terminated = True
                except Exception as wait_kill_err:
                     monitor_logger.error(f"等待進程 {proc_info['pid']} 強制結束時出錯: {wait_kill_err}", exc_info=False)

                monitor_logger.info(f"已處理匹配的進程 PID: {proc_info['pid']}，停止搜索。(Processed matching process PID: {proc_info['pid']}, stopping search.)")
                break # Exit the loop once a process is handled
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
             pass # Process might have already exited, access denied, or is a zombie
        except Exception as e:
            pid_str = proc.pid if hasattr(proc, 'pid') else 'N/A'
            monitor_logger.error(f"檢查或終止進程 PID:{pid_str} 時出錯: {e}", exc_info=False)

    if process_found and not terminated:
         monitor_logger.error("找到遊戲進程但未能成功終止它。(Found game process but failed to terminate it successfully.)")
    elif not process_found:
        monitor_logger.warning(f"未找到名稱為 '{target_process_name}' 的正在運行的進程。(No running process named '{target_process_name}' was found.)")

    # Wait a moment before restarting, use the launcher path from config
    time.sleep(2)
    if not launcher_path or not os.path.exists(os.path.dirname(launcher_path)):
         monitor_logger.error(f"遊戲啟動器路徑 '{launcher_path}' 無效或目錄不存在，無法啟動。(Game launcher path '{launcher_path}' is invalid or directory does not exist, cannot launch.)")
         return

    monitor_logger.info(f"正在使用啟動器啟動遊戲: {launcher_path} (Launching game using launcher: {launcher_path})")
    try:
        if sys.platform == "win32":
            os.startfile(launcher_path)
            monitor_logger.info("已調用 os.startfile 啟動遊戲。(os.startfile called to launch game.)")
        else:
            subprocess.Popen([launcher_path])
            monitor_logger.info("已調用 subprocess.Popen 啟動遊戲。(subprocess.Popen called to launch game.)")
    except FileNotFoundError:
        monitor_logger.error(f"啟動錯誤：找不到遊戲啟動器 '{launcher_path}'。(Launch Error: Game launcher not found at '{launcher_path}'.)")
    except OSError as ose:
         monitor_logger.error(f"啟動錯誤 (OSError): {ose} - 檢查路徑和權限。(Launch Error (OSError): {ose} - Check path and permissions.)", exc_info=True)
    except Exception as e:
        monitor_logger.error(f"啟動遊戲時發生未預期錯誤: {e}", exc_info=True)

def perform_scheduled_restart():
    """Handles the sequence of pausing UI, restarting game, resuming UI."""
    monitor_logger.info("開始執行定時重啟流程。(Starting scheduled restart sequence.)")

    # 1. Signal main process to pause UI monitoring via stdout
    pause_signal_data = {'action': 'pause_ui'}
    try:
        json_signal = json.dumps(pause_signal_data)
        monitor_logger.info(f"準備發送暫停訊號: {json_signal} (Preparing to send pause signal)") # Log before print
        print(json_signal, flush=True)
        monitor_logger.info("已發送暫停 UI 監控訊號。(Sent pause UI monitoring signal.)")
    except Exception as e:
         monitor_logger.error(f"發送暫停訊號 '{json_signal}' 失敗: {e}", exc_info=True) # Log signal data on error

    # 2. Wait 1 minute
    monitor_logger.info("等待 60 秒以暫停 UI。(Waiting 60 seconds for UI pause...)")
    time.sleep(30)

    # 3. Restart the game
    restart_game_process()

    # 4. Wait 1 minute
    monitor_logger.info("等待 60 秒讓遊戲啟動。(Waiting 60 seconds for game to launch...)")
    time.sleep(30)

    # 5. Signal main process to resume UI monitoring via stdout
    resume_signal_data = {'action': 'resume_ui'}
    try:
        json_signal = json.dumps(resume_signal_data)
        monitor_logger.info(f"準備發送恢復訊號: {json_signal} (Preparing to send resume signal)") # Log before print
        print(json_signal, flush=True)
        monitor_logger.info("已發送恢復 UI 監控訊號。(Sent resume UI monitoring signal.)")
    except Exception as e:
         monitor_logger.error(f"發送恢復訊號 '{json_signal}' 失敗: {e}", exc_info=True) # Log signal data on error

    monitor_logger.info("定時重啟流程完成。(Scheduled restart sequence complete.)")
# Configure logger (basic example, adjust as needed)
# (Logging setup moved earlier)

def find_game_window(title=config.WINDOW_TITLE):
    """Attempts to find the game window by its title."""
    try:
        windows = gw.getWindowsWithTitle(title)
        if windows:
            return windows[0]
    except Exception as e:
        # Log errors if a logger was configured
        # monitor_logger.error(f"Error finding window '{title}': {e}")
        pass # Keep silent if window not found during normal check
    return None

def monitor_game_window():
    """The main monitoring loop. Now runs directly, not in a thread."""
    monitor_logger.info("遊戲視窗監控腳本已啟動。(Game window monitoring script started.)")
    last_adjustment_message = "" # Track last message to avoid spam
    next_restart_time = None

    # Initialize scheduled restart timer if enabled
    if config.ENABLE_SCHEDULED_RESTART and config.RESTART_INTERVAL_MINUTES > 0:
        interval_seconds = config.RESTART_INTERVAL_MINUTES * 60
        next_restart_time = time.time() + interval_seconds
        monitor_logger.info(f"已啟用定時重啟，首次重啟將在 {config.RESTART_INTERVAL_MINUTES} 分鐘後執行。(Scheduled restart enabled. First restart in {config.RESTART_INTERVAL_MINUTES} minutes.)")
    else:
        monitor_logger.info("未啟用定時重啟功能。(Scheduled restart is disabled.)")


    while True: # Run indefinitely until terminated externally
        # --- Scheduled Restart Check ---
        if next_restart_time and time.time() >= next_restart_time:
            monitor_logger.info("到達預定重啟時間。(Scheduled restart time reached.)")
            perform_scheduled_restart()
            # Reset timer for the next interval
            interval_seconds = config.RESTART_INTERVAL_MINUTES * 60
            next_restart_time = time.time() + interval_seconds
            monitor_logger.info(f"重啟計時器已重置，下次重啟將在 {config.RESTART_INTERVAL_MINUTES} 分鐘後執行。(Restart timer reset. Next restart in {config.RESTART_INTERVAL_MINUTES} minutes.)")
            # Continue to next loop iteration after restart sequence
            time.sleep(config.MONITOR_INTERVAL_SECONDS) # Add a small delay before next check
            continue

        # --- Regular Window Monitoring ---
        window = find_game_window()
        adjustment_made = False
        current_message = ""

        if window:
            try:
                hwnd = window._hWnd # Get the window handle for win32 functions

                # 1. Check and Adjust Position/Size
                current_pos = (window.left, window.top)
                current_size = (window.width, window.height)
                target_pos = (config.GAME_WINDOW_X, config.GAME_WINDOW_Y)
                target_size = (config.GAME_WINDOW_WIDTH, config.GAME_WINDOW_HEIGHT)

                if current_pos != target_pos or current_size != target_size:
                    window.moveTo(target_pos[0], target_pos[1])
                    window.resizeTo(target_size[0], target_size[1])
                    # Verify if move/resize was successful before logging
                    time.sleep(0.1) # Give window time to adjust
                    window.activate() # Bring window to foreground before checking again
                    time.sleep(0.1)
                    new_pos = (window.left, window.top)
                    new_size = (window.width, window.height)
                    if new_pos == target_pos and new_size == target_size:
                         current_message += f"已將遊戲視窗調整至位置 ({target_pos[0]},{target_pos[1]}) 大小 {target_size[0]}x{target_size[1]}。(Adjusted game window to position {target_pos} size {target_size}.) "
                         adjustment_made = True
                    else:
                         # Log failure if needed
                         # monitor_logger.warning(f"Failed to adjust window. Current: {new_pos} {new_size}, Target: {target_pos} {target_size}")
                         pass # Keep silent on failure for now

                # 2. Check and Set Topmost
                style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                is_topmost = style & win32con.WS_EX_TOPMOST

                if not is_topmost:
                    # Set topmost, -1 for HWND_TOPMOST, flags = SWP_NOMOVE | SWP_NOSIZE
                    win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                          win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
                    # Verify
                    time.sleep(0.1)
                    new_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                    if new_style & win32con.WS_EX_TOPMOST:
                        current_message += "已將遊戲視窗設為最上層。(Set game window to topmost.)"
                        adjustment_made = True
                    else:
                        # Log failure if needed
                        # monitor_logger.warning("Failed to set window to topmost.")
                        pass # Keep silent

            except gw.PyGetWindowException as e:
                # monitor_logger.warning(f"無法訪問視窗屬性 (可能已關閉): {e} (Could not access window properties (may be closed): {e})")
                pass # Window might have closed between find and access
            except Exception as e:
                monitor_logger.error(f"監控遊戲視窗時發生未預期錯誤: {e} (Unexpected error during game window monitoring: {e})", exc_info=True)

        # Print adjustment message only if an adjustment was made and it's different from the last one
        # This should NOT print JSON signals
        if adjustment_made and current_message and current_message != last_adjustment_message:
            # monitor_logger.info(f"遊戲視窗狀態已調整: {current_message.strip()}") # Log instead of print
            # Keep print for now for visibility of adjustments, but ensure ONLY JSON goes for signals
             # print(f"[GameMonitor] {current_message.strip()}") # REMOVED to prevent non-JSON output
             monitor_logger.info(f"[GameMonitor] {current_message.strip()}") # Log instead
             last_adjustment_message = current_message
        elif not window:
            # Reset last message if window disappears
            last_adjustment_message = ""

        # Wait before the next check
        time.sleep(config.MONITOR_INTERVAL_SECONDS)

    # This part is theoretically unreachable in the new design as the loop is infinite
    # and termination is handled externally by the parent process (main.py).
    # monitor_logger.info("遊戲視窗監控腳本已停止。(Game window monitoring script stopped.)")


# Example usage (if run directly)
if __name__ == '__main__':
    monitor_logger.info("直接運行 game_monitor.py。(Running game_monitor.py directly.)")
    monitor_logger.info(f"將監控標題為 '{config.WINDOW_TITLE}' 的視窗。(Will monitor window with title '{config.WINDOW_TITLE}')")
    monitor_logger.info(f"目標位置: ({config.GAME_WINDOW_X}, {config.GAME_WINDOW_Y}), 目標大小: {config.GAME_WINDOW_WIDTH}x{config.GAME_WINDOW_HEIGHT}")
    monitor_logger.info(f"檢查間隔: {config.MONITOR_INTERVAL_SECONDS} 秒。(Check interval: {config.MONITOR_INTERVAL_SECONDS} seconds.)")
    if config.ENABLE_SCHEDULED_RESTART:
         monitor_logger.info(f"定時重啟已啟用，間隔: {config.RESTART_INTERVAL_MINUTES} 分鐘。(Scheduled restart enabled, interval: {config.RESTART_INTERVAL_MINUTES} minutes.)")
    else:
         monitor_logger.info("定時重啟已禁用。(Scheduled restart disabled.)")
    monitor_logger.info("腳本將持續運行，請從啟動它的終端使用 Ctrl+C 或由父進程終止。(Script will run continuously. Stop with Ctrl+C from the launching terminal or termination by parent process.)")

    try:
        monitor_game_window() # Start the main loop directly
    except KeyboardInterrupt:
        monitor_logger.info("收到 Ctrl+C，正在退出...(Received Ctrl+C, exiting...)")
    except Exception as e:
        monitor_logger.critical(f"監控過程中發生致命錯誤: {e}", exc_info=True)
        sys.exit(1) # Exit with error code
    finally:
        monitor_logger.info("Game Monitor 腳本執行完畢。(Game Monitor script finished.)")

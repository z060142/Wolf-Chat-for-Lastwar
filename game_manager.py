#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Game Manager Module

Provides game window monitoring, automatic restart, and process management features.
Designed to be imported and controlled by setup.py or other management scripts.
"""

import os
import sys
import time
import json
import threading
import subprocess
import logging
import pygetwindow as gw

# Attempt to import platform-specific modules that might be needed
try:
    import win32gui
    import win32con
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False
    print("Warning: win32gui/win32con modules not installed, some window management features may be unavailable")

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    print("Warning: psutil module not installed, process management features may be unavailable")


class GameMonitor:
    """
    Game window monitoring class.
    Responsible for monitoring game window position, scheduled restarts, and providing window management functions.
    """
    def __init__(self, config_data, remote_data=None, logger=None, callback=None):
        # Use the provided logger or create a new one
        self.logger = logger or logging.getLogger("GameMonitor")
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

        self.config_data = config_data
        self.remote_data = remote_data or {}
        self.callback = callback  # Callback function to notify the caller

        # Read settings from configuration
        self.window_title = self.config_data.get("GAME_WINDOW_CONFIG", {}).get("WINDOW_TITLE", "Last War-Survival Game")
        self.enable_restart = self.config_data.get("GAME_WINDOW_CONFIG", {}).get("ENABLE_SCHEDULED_RESTART", True)
        self.restart_interval = self.config_data.get("GAME_WINDOW_CONFIG", {}).get("RESTART_INTERVAL_MINUTES", 60)
        self.game_path = self.config_data.get("GAME_WINDOW_CONFIG", {}).get("GAME_EXECUTABLE_PATH", "")
        self.window_x = self.config_data.get("GAME_WINDOW_CONFIG", {}).get("GAME_WINDOW_X", 50)
        self.window_y = self.config_data.get("GAME_WINDOW_CONFIG", {}).get("GAME_WINDOW_Y", 30)
        self.window_width = self.config_data.get("GAME_WINDOW_CONFIG", {}).get("GAME_WINDOW_WIDTH", 600)
        self.window_height = self.config_data.get("GAME_WINDOW_CONFIG", {}).get("GAME_WINDOW_HEIGHT", 1070)
        self.monitor_interval = self.config_data.get("GAME_WINDOW_CONFIG", {}).get("MONITOR_INTERVAL_SECONDS", 5)

        # Read game process name from remote_data, use default if not found
        self.game_process_name = self.remote_data.get("GAME_PROCESS_NAME", "LastWar.exe")

        # Internal state
        self.running = False
        self.next_restart_time = None
        self.monitor_thread = None
        self.stop_event = threading.Event()

        # Add these tracking variables
        self.last_focus_failure_count = 0
        self.last_successful_foreground = time.time()

        self.logger.info(f"GameMonitor initialized. Game window: '{self.window_title}', Process: '{self.game_process_name}'")
        self.logger.info(f"Position: ({self.window_x}, {self.window_y}), Size: {self.window_width}x{self.window_height}")
        self.logger.info(f"Scheduled Restart: {'Enabled' if self.enable_restart else 'Disabled'}, Interval: {self.restart_interval} minutes")

    def start(self):
        """Start game window monitoring"""
        if self.running:
            self.logger.info("Game window monitoring is already running")
            return True # Return True if already running

        self.logger.info("Starting game window monitoring...")
        self.stop_event.clear()

        # Set next restart time
        if self.enable_restart and self.restart_interval > 0:
            self.next_restart_time = time.time() + (self.restart_interval * 60)
            self.logger.info(f"Scheduled restart enabled. First restart in {self.restart_interval} minutes")
        else:
            self.next_restart_time = None
            self.logger.info("Scheduled restart is disabled")

        # Start monitoring thread
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        self.running = True
        self.logger.info("Game window monitoring started")
        return True

    def stop(self):
        """Stop game window monitoring"""
        if not self.running:
            self.logger.info("Game window monitoring is not running")
            return True # Return True if already stopped

        self.logger.info("Stopping game window monitoring...")
        self.stop_event.set()

        # Wait for monitoring thread to finish
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.logger.info("Waiting for monitoring thread to finish...")
            self.monitor_thread.join(timeout=5)
            if self.monitor_thread.is_alive():
                self.logger.warning("Game window monitoring thread did not stop within the timeout period")

        self.running = False
        self.monitor_thread = None
        self.logger.info("Game window monitoring stopped")
        return True

    def _monitor_loop(self):
        """Main monitoring loop"""
        self.logger.info("Game window monitoring loop started")
        last_adjustment_message = ""  # Avoid logging repetitive adjustment messages

        while not self.stop_event.is_set():
            try:
                # Check for scheduled restart
                if self.next_restart_time and time.time() >= self.next_restart_time:
                    self.logger.info("Scheduled restart time reached. Performing restart...")
                    self._perform_restart()
                    # Reset next restart time
                    self.next_restart_time = time.time() + (self.restart_interval * 60)
                    self.logger.info(f"Restart timer reset. Next restart in {self.restart_interval} minutes")
                    # Continue to next loop iteration
                    time.sleep(self.monitor_interval)
                    continue

                # Find game window
                window = self._find_game_window()
                adjustment_made = False
                current_message = ""

                if window:
                    try:
                        # Use win32gui functions only on Windows
                        if HAS_WIN32:
                            # Get window handle
                            hwnd = window._hWnd

                            # 1. Check and adjust position/size
                            current_pos = (window.left, window.top)
                            current_size = (window.width, window.height)
                            target_pos = (self.window_x, self.window_y)
                            target_size = (self.window_width, self.window_height)

                            if current_pos != target_pos or current_size != target_size:
                                window.moveTo(target_pos[0], target_pos[1])
                                window.resizeTo(target_size[0], target_size[1])
                                time.sleep(0.1)
                                window.activate()
                                time.sleep(0.1)
                                # Check if changes were successful
                                new_pos = (window.left, window.top)
                                new_size = (window.width, window.height)
                                if new_pos == target_pos and new_size == target_size:
                                    current_message += f"Adjusted window position/size. "
                                    adjustment_made = True

                            # 2. Check and bring to foreground using enhanced method
                            current_foreground_hwnd = win32gui.GetForegroundWindow()
                            if current_foreground_hwnd != hwnd:
                                # Use enhanced forceful focus method
                                success, method_used = self._force_window_foreground(hwnd, window)
                                if success:
                                    current_message += f"Focused window using {method_used}. "
                                    adjustment_made = True
                                    if not hasattr(self, 'last_focus_failure_count'):
                                        self.last_focus_failure_count = 0
                                    self.last_focus_failure_count = 0
                                else:
                                    # Increment failure counter
                                    if not hasattr(self, 'last_focus_failure_count'):
                                        self.last_focus_failure_count = 0
                                    self.last_focus_failure_count += 1
                                    
                                    # Log warning with consecutive failure count
                                    self.logger.warning(f"Window focus failed (attempt {self.last_focus_failure_count}): {method_used}")
                                    
                                    # Restart game after too many failures
                                    if self.last_focus_failure_count >= 15:
                                        self.logger.warning("Excessive focus failures, restarting game...")
                                        self._perform_restart()
                                        self.last_focus_failure_count = 0
                        else:
                            # Use basic functions on non-Windows platforms
                            current_pos = (window.left, window.top)
                            current_size = (window.width, window.height)
                            target_pos = (self.window_x, self.window_y)
                            target_size = (self.window_width, self.window_height)

                            if current_pos != target_pos or current_size != target_size:
                                window.moveTo(target_pos[0], target_pos[1])
                                window.resizeTo(target_size[0], target_size[1])
                                current_message += f"Adjusted game window to position {target_pos} size {target_size[0]}x{target_size[1]}. "
                                adjustment_made = True

                            # Try activating the window (may have limited effect on non-Windows)
                            try:
                                window.activate()
                                current_message += "Attempted to activate game window. "
                                adjustment_made = True
                            except Exception as activate_err:
                                self.logger.warning(f"Error activating window: {activate_err}")
                                
                    except Exception as e:
                        self.logger.error(f"Unexpected error while monitoring game window: {e}")

                # Log only if adjustments were made and the message changed
                if adjustment_made and current_message and current_message != last_adjustment_message:
                    self.logger.info(f"[GameMonitor] {current_message.strip()}")
                    last_adjustment_message = current_message
                elif not window:
                    # Reset last message if window disappears
                    last_adjustment_message = ""

            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")

            # Wait for the next check
            time.sleep(self.monitor_interval)

        self.logger.info("Game window monitoring loop finished")

    def _find_game_window(self):
        """Find the game window with the specified title"""
        try:
            windows = gw.getWindowsWithTitle(self.window_title)
            if windows:
                return windows[0]
        except Exception as e:
            self.logger.debug(f"Error finding game window: {e}")
        return None

    def _force_window_foreground(self, hwnd, window):
        """Aggressive window focus implementation"""
        if not HAS_WIN32:
            return False, "win32 modules unavailable"
            
        success = False
        methods_tried = []
        
        # Method 1: HWND_TOPMOST strategy
        methods_tried.append("HWND_TOPMOST")
        try:
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                             win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
            time.sleep(0.1)
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, 0, 0, 0, 0,
                             win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
            
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.2)
            if win32gui.GetForegroundWindow() == hwnd:
                return True, "HWND_TOPMOST"
        except Exception as e:
            self.logger.debug(f"Method 1 failed: {e}")

        # Method 2: Minimize/restore cycle
        methods_tried.append("MinimizeRestore")
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            time.sleep(0.3)
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.2)
            win32gui.SetForegroundWindow(hwnd)
            
            if win32gui.GetForegroundWindow() == hwnd:
                return True, "MinimizeRestore"
        except Exception as e:
            self.logger.debug(f"Method 2 failed: {e}")

        # Method 3: Thread input attach
        methods_tried.append("ThreadAttach")
        try:
            import win32process
            import win32api
            
            current_thread_id = win32api.GetCurrentThreadId()
            window_thread_id = win32process.GetWindowThreadProcessId(hwnd)[0]
            
            if current_thread_id != window_thread_id:
                win32process.AttachThreadInput(current_thread_id, window_thread_id, True)
                try:
                    win32gui.BringWindowToTop(hwnd)
                    win32gui.SetForegroundWindow(hwnd)
                    
                    time.sleep(0.2)
                    if win32gui.GetForegroundWindow() == hwnd:
                        return True, "ThreadAttach"
                finally:
                    win32process.AttachThreadInput(current_thread_id, window_thread_id, False)
        except Exception as e:
            self.logger.debug(f"Method 3 failed: {e}")

        # Method 4: Flash + Window messages
        methods_tried.append("Flash+Messages")
        try:
            # First flash to get attention
            win32gui.FlashWindow(hwnd, True)
            time.sleep(0.2)
            
            # Then send specific window messages
            win32gui.SendMessage(hwnd, win32con.WM_SETREDRAW, 0, 0)
            win32gui.SendMessage(hwnd, win32con.WM_SETREDRAW, 1, 0)
            win32gui.RedrawWindow(hwnd, None, None, 
                                 win32con.RDW_FRAME | win32con.RDW_INVALIDATE | 
                                 win32con.RDW_UPDATENOW | win32con.RDW_ALLCHILDREN)
                                 
            win32gui.PostMessage(hwnd, win32con.WM_SYSCOMMAND, win32con.SC_RESTORE, 0)
            win32gui.PostMessage(hwnd, win32con.WM_ACTIVATE, win32con.WA_ACTIVE, 0)
            
            time.sleep(0.2)
            if win32gui.GetForegroundWindow() == hwnd:
                return True, "Flash+Messages"
        except Exception as e:
            self.logger.debug(f"Method 4 failed: {e}")

        # Method 5: Hide/Show cycle
        methods_tried.append("HideShow")
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
            time.sleep(0.2)
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
            time.sleep(0.2)
            win32gui.SetForegroundWindow(hwnd)
            
            if win32gui.GetForegroundWindow() == hwnd:
                return True, "HideShow"
        except Exception as e:
            self.logger.debug(f"Method 5 failed: {e}")

        return False, f"All methods failed: {', '.join(methods_tried)}"

    def _find_game_process_by_window(self):
        """Find process using both window title and process name"""
        if not HAS_PSUTIL or not HAS_WIN32:
            return None

        try:
            window = self._find_game_window()
            if not window:
                return None

            hwnd = window._hWnd
            window_pid = None
            try:
                import win32process
                _, window_pid = win32process.GetWindowThreadProcessId(hwnd)
            except Exception:
                return None

            if window_pid:
                try:
                    proc = psutil.Process(window_pid)
                    proc_name = proc.name()
                    
                    if proc_name.lower() == self.game_process_name.lower():
                        self.logger.info(f"Found game process '{proc_name}' (PID: {proc.pid}) with window title '{self.window_title}'")
                        return proc
                    else:
                        self.logger.debug(f"Window process name mismatch: expected '{self.game_process_name}', got '{proc_name}'")
                        return proc # Returning proc even if name mismatches, as per user's code.
                except Exception:
                    pass
            
            # Fallback to name-based search if window-based fails or PID doesn't match process name.
            # The user's provided code implies a fallback to _find_game_process_by_name()
            # This will be handled by the updated _find_game_process method.
            # For now, if the window PID didn't lead to a matching process name, we return None here.
            # The original code had "return self._find_game_process_by_name()" here,
            # but that would create a direct dependency. The new _find_game_process handles the fallback.
            # So, if we reach here, it means the window was found, PID was obtained, but process name didn't match.
            # The original code returns `proc` even on mismatch, so I'll keep that.
            # If `window_pid` was None or `psutil.Process(window_pid)` failed, it would have returned None or passed.
            # The logic "return self._find_game_process_by_name()" was in the original snippet,
            # I will include it here as per the snippet, but note that the overall _find_game_process will also call it.
            return self._find_game_process_by_name() # As per user snippet
            
        except Exception as e:
            self.logger.error(f"Process-by-window lookup error: {e}")
            return None

    def _find_game_process(self):
        """Find game process with combined approach"""
        # Try window-based process lookup first
        proc = self._find_game_process_by_window()
        if proc:
            return proc
            
        # Fall back to name-only lookup
        # This is the original _find_game_process logic, now as a fallback.
        if not HAS_PSUTIL:
            self.logger.debug("psutil not available for name-only process lookup fallback.") # Changed to debug as primary is window based
            return None
        try:
            for p_iter in psutil.process_iter(['pid', 'name', 'exe']):
                try:
                    proc_info = p_iter.info
                    proc_name = proc_info.get('name')
                    if proc_name and proc_name.lower() == self.game_process_name.lower():
                        self.logger.info(f"Found game process by name '{proc_name}' (PID: {p_iter.pid}) as fallback")
                        return p_iter
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
        except Exception as e:
            self.logger.error(f"Error in name-only game process lookup: {e}")
        
        self.logger.info(f"Game process '{self.game_process_name}' not found by name either.")
        return None

    def _perform_restart(self):
        """Execute the game restart process"""
        self.logger.info("Starting game restart process")

        try:
            # 1. Notify that restart has begun (optional)
            if self.callback:
                self.callback("restart_begin")

            # 2. Terminate existing game process
            self._terminate_game_process()
            time.sleep(2)  # Short wait to ensure process termination

            # 3. Start new game process
            if self._start_game_process():
                self.logger.info("Game restarted successfully")
            else:
                self.logger.error("Failed to start game")

            # 4. Wait for game to launch
            restart_wait_time = 45  # seconds, increased from 30
            self.logger.info(f"Waiting for game to start ({restart_wait_time} seconds)...")
            time.sleep(restart_wait_time)

            # 5. Notify restart completion
            self.logger.info("Game restart process completed, sending notification")
            if self.callback:
                self.callback("restart_complete")

            return True
        except Exception as e:
            self.logger.error(f"Error during game restart process: {e}")
            # Attempt to notify error
            if self.callback:
                self.callback("restart_error")
            return False

    def _terminate_game_process(self):
        """Terminate the game process"""
        self.logger.info(f"Attempting to terminate game process '{self.game_process_name}'")

        if not HAS_PSUTIL:
            self.logger.warning("psutil is not available, cannot terminate process")
            return False

        process = self._find_game_process()
        terminated = False

        if process:
            try:
                self.logger.info(f"Found game process PID: {process.pid}, terminating...")
                process.terminate()

                try:
                    process.wait(timeout=5)
                    self.logger.info(f"Process {process.pid} terminated successfully (terminate)")
                    terminated = True
                except psutil.TimeoutExpired:
                    self.logger.warning(f"Process {process.pid} did not terminate within 5s (terminate), attempting force kill")
                    process.kill()
                    process.wait(timeout=5)
                    self.logger.info(f"Process {process.pid} force killed (kill)")
                    terminated = True
            except Exception as e:
                self.logger.error(f"Error terminating process: {e}")
        else:
            self.logger.warning(f"No running process found with name '{self.game_process_name}'")

        return terminated

    def _start_game_process(self):
        """Start the game process"""
        if not self.game_path:
            self.logger.error("Game executable path not set, cannot start")
            return False

        self.logger.info(f"Starting game: {self.game_path}")
        try:
            if sys.platform == "win32":
                os.startfile(self.game_path)
                self.logger.info("Called os.startfile to launch game")
                return True
            else:
                # Use subprocess.Popen for non-Windows platforms
                # Ensure it runs detached if possible, or handle appropriately
                subprocess.Popen([self.game_path], start_new_session=True) # Attempt detached start
                self.logger.info("Called subprocess.Popen to launch game")
                return True
        except FileNotFoundError:
            self.logger.error(f"Startup error: Game launcher '{self.game_path}' not found")
        except OSError as ose:
            self.logger.error(f"Startup error (OSError): {ose} - Check path and permissions", exc_info=True)
        except Exception as e:
            self.logger.error(f"Unexpected error starting game: {e}", exc_info=True)

        return False

    def restart_now(self):
        """Perform an immediate restart"""
        self.logger.info("Manually triggering game restart")
        result = self._perform_restart()

        # Reset the timer if scheduled restart is enabled
        if self.enable_restart and self.restart_interval > 0:
            self.next_restart_time = time.time() + (self.restart_interval * 60)
            self.logger.info(f"Restart timer reset. Next restart in {self.restart_interval} minutes")

        return result

    def update_config(self, config_data=None, remote_data=None):
        """Update configuration settings"""
        if config_data:
            old_config = self.config_data
            self.config_data = config_data

            # Update key settings
            self.window_title = self.config_data.get("GAME_WINDOW_CONFIG", {}).get("WINDOW_TITLE", self.window_title)
            self.enable_restart = self.config_data.get("GAME_WINDOW_CONFIG", {}).get("ENABLE_SCHEDULED_RESTART", self.enable_restart)
            self.restart_interval = self.config_data.get("GAME_WINDOW_CONFIG", {}).get("RESTART_INTERVAL_MINUTES", self.restart_interval)
            self.game_path = self.config_data.get("GAME_WINDOW_CONFIG", {}).get("GAME_EXECUTABLE_PATH", self.game_path)
            self.window_x = self.config_data.get("GAME_WINDOW_CONFIG", {}).get("GAME_WINDOW_X", self.window_x)
            self.window_y = self.config_data.get("GAME_WINDOW_CONFIG", {}).get("GAME_WINDOW_Y", self.window_y)
            self.window_width = self.config_data.get("GAME_WINDOW_CONFIG", {}).get("GAME_WINDOW_WIDTH", self.window_width)
            self.window_height = self.config_data.get("GAME_WINDOW_CONFIG", {}).get("GAME_WINDOW_HEIGHT", self.window_height)
            self.monitor_interval = self.config_data.get("GAME_WINDOW_CONFIG", {}).get("MONITOR_INTERVAL_SECONDS", self.monitor_interval)

            # Reset scheduled restart timer if parameters changed
            if self.running and self.enable_restart and self.restart_interval > 0:
                old_interval = old_config.get("GAME_WINDOW_CONFIG", {}).get("RESTART_INTERVAL_MINUTES", 60)
                if self.restart_interval != old_interval:
                    self.next_restart_time = time.time() + (self.restart_interval * 60)
                    self.logger.info(f"Restart interval updated to {self.restart_interval} minutes, next restart reset")

        if remote_data:
            self.remote_data = remote_data
            old_process_name = self.game_process_name
            self.game_process_name = self.remote_data.get("GAME_PROCESS_NAME", old_process_name)
            if self.game_process_name != old_process_name:
                self.logger.info(f"Game process name updated to '{self.game_process_name}'")

        self.logger.info("GameMonitor configuration updated")


# Provide simple external API functions
def create_game_monitor(config_data, remote_data=None, logger=None, callback=None):
    """Create a game monitor instance"""
    return GameMonitor(config_data, remote_data, logger, callback)

def stop_all_monitors():
    """Attempt to stop all created monitors (global cleanup)"""
    # This function could be implemented if instance references are stored.
    # In the current design, each monitor needs to be stopped individually.
    pass


# Functionality when run standalone (similar to original game_monitor.py)
if __name__ == "__main__":
    # Set up basic logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger("GameManagerStandalone")

    # Load settings from config.py
    try:
        import config
        logger.info("Loaded config.py")

        # Build basic configuration dictionary
        config_data = {
            "GAME_WINDOW_CONFIG": {
                "WINDOW_TITLE": config.WINDOW_TITLE,
                "ENABLE_SCHEDULED_RESTART": config.ENABLE_SCHEDULED_RESTART,
                "RESTART_INTERVAL_MINUTES": config.RESTART_INTERVAL_MINUTES,
                "GAME_EXECUTABLE_PATH": config.GAME_EXECUTABLE_PATH,
                "GAME_WINDOW_X": config.GAME_WINDOW_X,
                "GAME_WINDOW_Y": config.GAME_WINDOW_Y,
                "GAME_WINDOW_WIDTH": config.GAME_WINDOW_WIDTH,
                "GAME_WINDOW_HEIGHT": config.GAME_WINDOW_HEIGHT,
                "MONITOR_INTERVAL_SECONDS": config.MONITOR_INTERVAL_SECONDS
            }
        }
        
        # Define a callback for standalone execution
        def standalone_callback(action):
            """Send JSON signal via standard output"""
            logger.info(f"Sending signal: {action}")
            signal_data = {'action': action}
            try:
                json_signal = json.dumps(signal_data)
                print(json_signal, flush=True)
                logger.info(f"Signal sent: {action}")
            except Exception as e:
                logger.error(f"Failed to send signal '{action}': {e}")

        # Create and start the monitor
        monitor = GameMonitor(config_data, logger=logger, callback=standalone_callback)
        monitor.start()

        # Keep the program running
        try:
            logger.info("Game monitoring started. Press Ctrl+C to stop.")
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Ctrl+C received, stopping...")
        finally:
            monitor.stop()
            logger.info("Game monitoring stopped")

    except ImportError:
        logger.error("Could not load config.py. Ensure it exists and contains necessary settings.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error starting game monitoring: {e}", exc_info=True)
        sys.exit(1)

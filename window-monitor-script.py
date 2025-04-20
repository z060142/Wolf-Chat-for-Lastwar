#!/usr/bin/env python
"""
Game Window Monitor Script - Keep game window on top and in position

This script monitors a specified game window, ensuring it stays
always on top and at the desired screen coordinates.
"""

import time
import argparse
import pygetwindow as gw
import win32gui
import win32con

def find_window_by_title(window_title):
    """Find the first window matching the title."""
    try:
        windows = gw.getWindowsWithTitle(window_title)
        if windows:
            return windows[0]
    except Exception as e:
        # pygetwindow can sometimes raise exceptions if a window disappears
        # during enumeration. Ignore these for monitoring purposes.
        # print(f"Error finding window: {e}") 
        pass
    return None

def set_window_always_on_top(hwnd):
    """Set the window to be always on top."""
    try:
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                              win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)
        # print(f"Window {hwnd} set to always on top.")
    except Exception as e:
        print(f"Error setting window always on top: {e}")

def move_window_if_needed(window, target_x, target_y):
    """Move the window to the target coordinates if it's not already there."""
    try:
        current_x, current_y = window.topleft
        if current_x != target_x or current_y != target_y:
            print(f"Window moved from ({current_x}, {current_y}). Moving back to ({target_x}, {target_y}).")
            window.moveTo(target_x, target_y)
            # print(f"Window moved to ({target_x}, {target_y}).")
    except gw.PyGetWindowException as e:
         # Handle cases where the window might close unexpectedly
         print(f"Error accessing window properties (might be closed): {e}")
    except Exception as e:
        print(f"Error moving window: {e}")

def main():
    parser = argparse.ArgumentParser(description='Game Window Monitor Tool')
    parser.add_argument('--window_title', default="Last War-Survival Game", help='Game window title to monitor')
    parser.add_argument('--x', type=int, default=50, help='Target window X coordinate')
    parser.add_argument('--y', type=int, default=30, help='Target window Y coordinate')
    parser.add_argument('--interval', type=float, default=1.0, help='Check interval in seconds')
    
    args = parser.parse_args()
    
    print(f"Monitoring window: '{args.window_title}'")
    print(f"Target position: ({args.x}, {args.y})")
    print(f"Check interval: {args.interval} seconds")
    print("Press Ctrl+C to stop.")

    hwnd = None
    last_hwnd_check_time = 0

    try:
        while True:
            current_time = time.time()
            window = None

            # Find window handle (HWND) - less frequent check if already found
            # pygetwindow can be slow, so avoid calling it too often if we have a valid handle
            if not hwnd or current_time - last_hwnd_check_time > 5: # Re-check HWND every 5 seconds
                 window_obj = find_window_by_title(args.window_title)
                 if window_obj:
                     # Get the HWND (window handle) needed for win32gui
                     # Accessing _hWnd is using an internal attribute, but it's common practice with pygetwindow
                     try:
                         hwnd = window_obj._hWnd 
                         window = window_obj # Keep the pygetwindow object for position checks
                         last_hwnd_check_time = current_time
                         # print(f"Found window HWND: {hwnd}")
                     except AttributeError:
                         print("Could not get HWND from window object. Retrying...")
                         hwnd = None
                 else:
                     if hwnd:
                         print(f"Window '{args.window_title}' lost.")
                     hwnd = None # Reset hwnd if window not found

            if hwnd:
                 # Ensure it's always on top
                 set_window_always_on_top(hwnd)

                 # Check and correct position using the pygetwindow object if available
                 # Re-find the pygetwindow object if needed for position check
                 if not window: 
                     window = find_window_by_title(args.window_title)
                 
                 if window:
                     move_window_if_needed(window, args.x, args.y)
                 else:
                     # If we have hwnd but can't get pygetwindow object, maybe it's closing
                     print(f"Have HWND {hwnd} but cannot get window object for position check.")
                     hwnd = None # Force re-find next cycle

            else:
                # print(f"Window '{args.window_title}' not found. Waiting...")
                pass # Wait for the window to appear

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\nMonitoring stopped by user.")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")

if __name__ == "__main__":
    main()

#!/usr/bin/env python
"""
Game Window Setup Script - Adjust game window position and size

This script will launch the game and adjust its window to a specified position and size (100,100 1280x768),
making it easier to take screenshots of UI elements for later use.
"""

import os
import time
import subprocess
import pygetwindow as gw
import psutil
import argparse

def is_process_running(process_name):
    """Check if a specified process is currently running"""
    for proc in psutil.process_iter(['name']):
        if proc.info['name'].lower() == process_name.lower():
            return True
    return False

def launch_game(game_path):
    """Launch the game"""
    if not os.path.exists(game_path):
        print(f"Error: Game executable not found at {game_path}")
        return False
    
    print(f"Launching game: {game_path}")
    subprocess.Popen(game_path)
    return True

def find_game_window(window_title, max_wait=30):
    """Find the game window"""
    print(f"Searching for game window: {window_title}")
    
    start_time = time.time()
    while time.time() - start_time < max_wait:
        try:
            windows = gw.getWindowsWithTitle(window_title)
            if windows:
                return windows[0]
        except Exception as e:
            print(f"Error finding window: {e}")
        
        print("Window not found, waiting 1 second before retrying...")
        time.sleep(1)
    
    print(f"Error: Game window not found within {max_wait} seconds")
    return None

def set_window_position_size(window, x, y, width, height):
    """Set window position and size"""
    try:
        print(f"Adjusting window position to ({x}, {y}) and size to {width}x{height}")
        window.moveTo(x, y)
        window.resizeTo(width, height)
        print("Window adjustment completed")
        return True
    except Exception as e:
        print(f"Error adjusting window: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Game Window Setup Tool')
    parser.add_argument('--launch', action='store_true', help='Whether to launch the game')
    parser.add_argument('--game_path', default=r"C:\Users\Bigspring\AppData\Local\TheLastWar\Launch.exe", help='Game launcher path')
    parser.add_argument('--window_title', default="Last War-Survival Game", help='Game window title')
    parser.add_argument('--process_name', default="LastWar.exe", help='Game process name')
    parser.add_argument('--x', type=int, default=50, help='Window X coordinate')
    parser.add_argument('--y', type=int, default=30, help='Window Y coordinate')
    parser.add_argument('--width', type=int, default=600, help='Window width')
    parser.add_argument('--height', type=int, default=1070, help='Window height')
    
    args = parser.parse_args()
    
    # Check if game is already running
    if not is_process_running(args.process_name):
        if args.launch:
            # Launch the game
            if not launch_game(args.game_path):
                return
        else:
            print(f"Game process {args.process_name} is not running, please launch the game first or use the --launch parameter")
            return
    else:
        print(f"Game process {args.process_name} is already running")
    
    # Find game window
    window = find_game_window(args.window_title)
    if not window:
        return
    
    # Set window position and size
    set_window_position_size(window, args.x, args.y, args.width, args.height)
    
    # Display final window state
    print("\nFinal window state:")
    print(f"Position: ({window.left}, {window.top})")
    print(f"Size: {window.width}x{window.height}")

if __name__ == "__main__":
    main()

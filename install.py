#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Wolf Chat Installation Script
Installs required dependencies for Wolf Chat
"""

import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox

LOCK_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements.lock.txt")


def _count_locked_packages():
    try:
        with open(LOCK_FILE, encoding="utf-8") as f:
            return sum(1 for line in f if "==" in line and not line.lstrip().startswith("#"))
    except OSError:
        return 0


def install_requirements(progress_var=None, status_label=None, root=None):
    """Sync this interpreter's environment to requirements.lock.txt (same as start.bat)"""
    if not os.path.exists(LOCK_FILE):
        message = f"Lock file not found: {LOCK_FILE}"
        print(message)
        if status_label:
            status_label.config(text=message)
        return False, message

    # Prefer uv (the .venv is created by uv and has no pip); fall back to pip
    commands = [
        ["uv", "pip", "sync", "--python", sys.executable, LOCK_FILE],
        [sys.executable, "-m", "pip", "install", "-r", LOCK_FILE],
    ]
    if status_label:
        status_label.config(text="Syncing dependencies with requirements.lock.txt...")
    if progress_var:
        progress_var.set(10)
    if root:
        root.update()

    last_error = ""
    for cmd in commands:
        try:
            print(f"Running: {' '.join(cmd)}")
            process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            print(process.stdout)
            if process.returncode == 0:
                message = f"Dependencies synced with requirements.lock.txt ({_count_locked_packages()} packages)."
                if progress_var:
                    progress_var.set(100)
                if status_label:
                    status_label.config(text=message)
                return True, message
            last_error = process.stdout.strip().splitlines()[-1] if process.stdout.strip() else f"exit code {process.returncode}"
        except FileNotFoundError as e:
            last_error = str(e)
        print(f"Failed: {last_error}")

    if progress_var:
        progress_var.set(100)
    message = f"Dependency sync failed: {last_error}. Close the bot and run start.bat instead."
    if status_label:
        status_label.config(text=message)
    return False, message

def run_installer_gui():
    """Run a simple GUI for the installer"""
    root = tk.Tk()
    root.title("Wolf Chat Installer")
    root.geometry("400x200")
    root.resizable(False, False)
    
    # Main frame
    main_frame = ttk.Frame(root, padding=20)
    main_frame.pack(fill=tk.BOTH, expand=True)
    
    # Title
    title_label = ttk.Label(main_frame, text="Wolf Chat Dependency Installer", font=("", 12, "bold"))
    title_label.pack(pady=(0, 10))
    
    # Info text
    info_text = f"This will sync {_count_locked_packages()} locked packages for Wolf Chat."
    info_label = ttk.Label(main_frame, text=info_text)
    info_label.pack(pady=(0, 15))
    
    # Progress bar
    progress_var = tk.DoubleVar()
    progress_bar = ttk.Progressbar(main_frame, variable=progress_var, maximum=100)
    progress_bar.pack(fill=tk.X, pady=(0, 10))
    
    # Status label
    status_label = ttk.Label(main_frame, text="Ready to install...")
    status_label.pack(pady=(0, 15))
    
    # Install button
    def start_installation():
        # Disable button during installation
        install_button.config(state=tk.DISABLED)
        
        # Run installation in a separate thread to keep UI responsive
        success, message = install_requirements(progress_var, status_label, root)
        
        # Show completion message
        if success:
            messagebox.showinfo("Installation Complete", message)
        else:
            messagebox.showwarning("Installation Issues", message)
        
        # Close the window
        root.destroy()
    
    install_button = ttk.Button(main_frame, text="Install Dependencies", command=start_installation)
    install_button.pack()
    
    # Start the GUI loop
    root.mainloop()

if __name__ == "__main__":
    # If run directly, show GUI
    run_installer_gui()
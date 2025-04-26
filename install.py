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

REQUIREMENTS = [
    "openai",
    "mcp",
    "pyautogui",
    "opencv-python",
    "numpy",
    "pyperclip",
    "pygetwindow",
    "psutil",
    "pywin32",
    "python-dotenv",
    "keyboard"
]

def install_requirements(progress_var=None, status_label=None, root=None):
    """Install all required packages using pip"""
    
    total = len(REQUIREMENTS)
    success_count = 0
    failed_packages = []
    
    for i, package in enumerate(REQUIREMENTS):
        if status_label:
            status_label.config(text=f"Installing {package}...")
        if progress_var:
            progress_var.set((i / total) * 100)
        if root:
            root.update()
        
        try:
            print(f"Installing {package}...")
            # Use subprocess to run pip install
            process = subprocess.run(
                [sys.executable, "-m", "pip", "install", package],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            print(f"Successfully installed {package}")
            success_count += 1
            
        except subprocess.CalledProcessError as e:
            print(f"Failed to install {package}: {e}")
            print(f"Error output: {e.stderr}")
            failed_packages.append(package)
            
        except Exception as e:
            print(f"Unexpected error installing {package}: {str(e)}")
            failed_packages.append(package)
    
    # Final progress update
    if progress_var:
        progress_var.set(100)
    
    # Report results
    if not failed_packages:
        result_message = f"All {success_count} packages installed successfully!"
        print(result_message)
        if status_label:
            status_label.config(text=result_message)
        return True, result_message
    else:
        result_message = f"Installed {success_count}/{total} packages. Failed: {', '.join(failed_packages)}"
        print(result_message)
        if status_label:
            status_label.config(text=result_message)
        return False, result_message

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
    info_text = f"This will install {len(REQUIREMENTS)} required packages for Wolf Chat."
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
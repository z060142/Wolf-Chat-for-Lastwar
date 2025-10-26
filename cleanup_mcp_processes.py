#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MCP Process Cleanup Utility

CRITICAL: This script forcefully terminates all MCP server processes.
It's designed to be called:
1. By Setup.py before restarting main.py
2. Manually when orphan MCP processes are detected
3. As a standalone cleanup tool

This prevents MCP server process leakage during automated restarts.
"""

import sys
import psutil
import time
import os

# MCP Server Process Signatures
# These patterns identify MCP server processes by command line
MCP_PROCESS_SIGNATURES = [
    # NPX-based servers (Exa)
    {
        'keywords': ['npx', 'exa-mcp-server'],
        'name': 'Exa MCP Server (npx)',
    },
    {
        'keywords': ['node', 'exa-mcp-server'],
        'name': 'Exa MCP Server (node)',
    },
    # UVX-based servers (Chroma)
    {
        'keywords': ['uvx', 'chroma-mcp'],
        'name': 'Chroma MCP Server (uvx)',
    },
    {
        'keywords': ['python', 'chroma-mcp'],
        'name': 'Chroma MCP Server (python)',
    },
    # Python-based servers (Position Tool)
    {
        'keywords': ['python', 'position_tool_server.py'],
        'name': 'Position Tool Server',
    },
    # Generic MCP patterns
    {
        'keywords': ['mcp-server', 'python'],
        'name': 'Generic MCP Server (python)',
    },
]

# MCP Communication Files
MCP_FILES = [
    "position_command.json",
    "position_result.json",
    "main_heartbeat.json",
    "chat_context.json",
]


def find_mcp_processes():
    """
    Find all running MCP server processes.

    Returns:
        list: List of (psutil.Process, signature_name) tuples
    """
    found_processes = []

    print("[MCP-CLEANUP] Scanning for MCP server processes...")

    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.cmdline()
            if not cmdline:
                continue

            cmdline_str = ' '.join(cmdline).lower()

            # Check against each signature
            for signature in MCP_PROCESS_SIGNATURES:
                keywords = signature['keywords']
                # All keywords must be present
                if all(keyword.lower() in cmdline_str for keyword in keywords):
                    found_processes.append((proc, signature['name']))
                    print(f"[MCP-CLEANUP] Found: {signature['name']} (PID: {proc.pid})")
                    print(f"              Command: {' '.join(cmdline[:3])}...")
                    break

        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    return found_processes


def terminate_process_tree(parent_proc, name):
    """
    Terminate a process and all its children.

    Args:
        parent_proc: psutil.Process object
        name: Human-readable name for logging

    Returns:
        bool: True if successful
    """
    try:
        pid = parent_proc.pid
        print(f"[MCP-CLEANUP] Terminating: {name} (PID: {pid})")

        # Get all children BEFORE terminating parent
        try:
            children = parent_proc.children(recursive=True)
            if children:
                print(f"              Found {len(children)} child process(es)")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            children = []

        # Terminate parent
        try:
            parent_proc.terminate()
            parent_proc.wait(timeout=3)
            print(f"              Terminated gracefully")
        except psutil.TimeoutExpired:
            print(f"              Timeout, killing forcefully...")
            parent_proc.kill()
            parent_proc.wait(timeout=2)
            print(f"              Killed")
        except psutil.NoSuchProcess:
            print(f"              Already terminated")

        # Terminate children
        for child in children:
            try:
                if child.is_running():
                    child.kill()
                    print(f"              Killed child PID: {child.pid}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        return True

    except psutil.NoSuchProcess:
        print(f"[MCP-CLEANUP] Process already gone: {name}")
        return True
    except psutil.AccessDenied:
        print(f"[MCP-CLEANUP] Access denied: {name} (PID: {pid})")
        return False
    except Exception as e:
        print(f"[MCP-CLEANUP] Error terminating {name}: {e}")
        return False


def cleanup_mcp_files():
    """Remove MCP communication files."""
    print("[MCP-CLEANUP] Cleaning up MCP communication files...")

    removed_count = 0
    for filename in MCP_FILES:
        try:
            if os.path.exists(filename):
                os.remove(filename)
                print(f"              Removed: {filename}")
                removed_count += 1
        except Exception as e:
            print(f"              Failed to remove {filename}: {e}")

    if removed_count == 0:
        print("              No files to clean")

    return removed_count


def main(verbose=True):
    """
    Main cleanup function.

    Args:
        verbose: Print detailed output

    Returns:
        int: Number of processes terminated
    """
    if verbose:
        print("=" * 60)
        print("MCP Process Cleanup Utility")
        print("=" * 60)

    # Find MCP processes
    mcp_processes = find_mcp_processes()

    if not mcp_processes:
        if verbose:
            print("[MCP-CLEANUP] No MCP server processes found")
        cleanup_mcp_files()
        return 0

    # Terminate each process
    terminated_count = 0
    failed_count = 0

    for proc, name in mcp_processes:
        if terminate_process_tree(proc, name):
            terminated_count += 1
        else:
            failed_count += 1

    # Summary
    if verbose:
        print("-" * 60)
        print(f"[MCP-CLEANUP] Summary:")
        print(f"              Terminated: {terminated_count}")
        if failed_count > 0:
            print(f"              Failed: {failed_count}")
        print("-" * 60)

    # Clean up files
    cleanup_mcp_files()

    return terminated_count


if __name__ == "__main__":
    # Parse command line arguments
    quiet_mode = "--quiet" in sys.argv or "-q" in sys.argv

    try:
        count = main(verbose=not quiet_mode)
        sys.exit(0)  # Always exit with 0 to not block Setup.py
    except KeyboardInterrupt:
        print("\n[MCP-CLEANUP] Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"[MCP-CLEANUP] Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

# test/llm_debug_script.py
# Purpose: Directly interact with the LLM for debugging, bypassing UI interaction.

import asyncio
import sys
import os
import json
import collections
import datetime
from contextlib import AsyncExitStack

# Assume these modules are in the parent directory or accessible via PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import config
import mcp_client
import llm_interaction
import chroma_client
from wolf_memory_bridge import WolfMemoryClient
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

# --- Parse CLI args ---
_arg_parser = argparse.ArgumentParser(add_help=False)
_arg_parser.add_argument("--test-memory", action="store_true",
    help="Use an isolated memories_test/ directory so debug sessions don't pollute real memory.")
_args, _ = _arg_parser.parse_known_args()

wolf_memory_client = WolfMemoryClient()

# --- Global Variables ---
active_mcp_sessions: dict[str, ClientSession] = {}
all_discovered_mcp_tools: list[dict] = []
exit_stack = AsyncExitStack()
wolfhart_persona_details: str | None = None
conversation_history = collections.deque(maxlen=20) # Shorter history for debugging
shutdown_requested = False

# --- Load Persona Function (Adapted from main.py) ---
def load_persona_from_file(filename="persona.json"):
    """Loads persona data from a local JSON file relative to the main script dir."""
    global wolfhart_persona_details
    try:
        # Get the directory of the main project, not the test directory
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        filepath = os.path.join(project_dir, filename)
        print(f"\nAttempting to load Persona data from: {filepath}")
        if not os.path.exists(filepath):
             raise FileNotFoundError(f"Persona file not found at {filepath}")

        with open(filepath, 'r', encoding='utf-8') as f:
            persona_data = json.load(f)
            wolfhart_persona_details = json.dumps(persona_data, ensure_ascii=False, indent=2)
            print(f"Successfully loaded Persona from '{filename}'.")

    except FileNotFoundError:
        print(f"Warning: Persona configuration file '{filename}' not found.")
        wolfhart_persona_details = None
    except json.JSONDecodeError:
        print(f"Error: Failed to parse Persona configuration file '{filename}'.")
        wolfhart_persona_details = None
    except Exception as e:
        print(f"Unknown error loading Persona configuration file '{filename}': {e}")
        wolfhart_persona_details = None

# --- Initialization Functions (Adapted from main.py) ---
async def connect_and_discover(key: str, server_config: dict):
    """Connects to a single MCP server, initializes, and discovers tools."""
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
        print(f"Starting stdio_client for Server '{key}'...")
        read, write = await exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        print(f"stdio_client for '{key}' active.")

        session = await exit_stack.enter_async_context(
            ClientSession(read, write)
        )
        print(f"ClientSession for '{key}' context entered.")

        print(f"Initializing Session '{key}' with 30s timeout...")
        try:
            await asyncio.wait_for(session.initialize(), timeout=30)
            print(f"Session '{key}' initialized successfully.")
        except asyncio.TimeoutError:
            print(f"ERROR: Session '{key}' initialization timed out after 30 seconds!")
            print(f"Skipping this MCP server. Check server startup logs for issues.")
            return  # Exit this function early to skip this server

        active_mcp_sessions[key] = session

        print(f"Discovering tools for Server '{key}'...")
        tools_as_dicts = await mcp_client.list_mcp_tools(session)
        if tools_as_dicts:
            processed_tools = []
            for tool_dict in tools_as_dicts:
                if isinstance(tool_dict, dict) and 'name' in tool_dict:
                    tool_dict['_server_key'] = key
                    processed_tools.append(tool_dict)
                else:
                    print(f"Warning: Unexpected tool format from '{key}': {tool_dict}")
            all_discovered_mcp_tools.extend(processed_tools)
            print(f"Processed {len(processed_tools)} tools from Server '{key}'.")
        else:
            print(f"Server '{key}' has no available tools.")

    except FileNotFoundError:
        print(f"==> Error: Command '{command}' for Server '{key}' not found. Check config.py. <==")
    except ConnectionRefusedError:
        print(f"==> Error: Connection to Server '{key}' refused. Is it running? <==")
    except Exception as e:
        print(f"==> Critical error initializing connection to Server '{key}': {e} <==")
        import traceback
        traceback.print_exc()

async def initialize_mcp_connections():
    """Concurrently starts and connects to all configured MCP servers."""
    print("--- Initializing MCP connections ---")
    connection_tasks = [
        asyncio.create_task(connect_and_discover(key, server_config), name=f"connect_{key}")
        for key, server_config in config.MCP_SERVERS.items()
    ]
    if connection_tasks:
        await asyncio.gather(*connection_tasks, return_exceptions=True)
    print("\n--- MCP connection initialization complete ---")
    print(f"Total discovered tools: {len(all_discovered_mcp_tools)}")
    print(f"Active Sessions: {list(active_mcp_sessions.keys())}")

# --- Cleanup Function (Adapted from main.py) ---
async def shutdown():
    """Gracefully closes MCP connections and wolf-memory subprocess."""
    global shutdown_requested
    if not shutdown_requested:
        print("Shutdown initiated.")
        shutdown_requested = True

    print(f"\nClosing MCP Server connections...")
    try:
        await exit_stack.aclose()
        print("AsyncExitStack closed.")
    except Exception as e:
        print(f"Error closing AsyncExitStack: {e}")
    finally:
        active_mcp_sessions.clear()
        all_discovered_mcp_tools.clear()
        wolf_memory_client.terminate()
        print("Cleanup completed.")

# --- Get Username Function ---
async def get_username():
    """Prompt the user for their name and return it."""
    print("\nPlease enter your name (or press Enter to use 'Debugger'): ", end="")
    user_input = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
    user_name = user_input.strip()
    if not user_name:
        user_name = "Debugger"  # Default name if nothing is entered
    return user_name

# --- Main Debug Loop ---
async def debug_loop():
    """Main loop for interactive LLM debugging."""
    global shutdown_requested, conversation_history

    # 1. Load Persona
    load_persona_from_file()

    # 2. Initialize memory system
    if getattr(config, 'WOLF_MEMORY_ENABLED', False):
        # Determine data directory
        if _args.test_memory:
            _wm_base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "wolf-memory")
            _data_dir = os.path.join(_wm_base, "memories_test")
            print(f"\n--- Starting Wolf Memory subprocess [TEST MODE: {_data_dir}] ---")
        else:
            _data_dir = ""
            print("\n--- Starting Wolf Memory subprocess ---")

        wolf_memory_client.start(
            backend=getattr(config, 'WOLF_MEMORY_BACKEND', ''),
            host=getattr(config, 'WOLF_MEMORY_HOST', ''),
            model=getattr(config, 'WOLF_MEMORY_MODEL', ''),
            data_dir=_data_dir,
        )
        print("---------------------------------------")
    else:
        print("\n--- Initializing ChromaDB ---")
        if not chroma_client.initialize_chroma_client():
            print("Warning: ChromaDB initialization failed. Memory functions may not work.")
        else:
            print("ChromaDB initialized successfully.")
        print("-----------------------------")

    # 3. Initialize MCP
    await initialize_mcp_connections()
    if not active_mcp_sessions:
        print("\nNo MCP servers connected. LLM tool usage will be limited. Continue? (y/n)")
        confirm = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
        if confirm.strip().lower() != 'y':
            return

    # 4. Get username
    user_name = await get_username()
    print(f"Debug session started as: {user_name}")

    print("\n--- LLM Debug Interface ---")
    print("Enter your message to the LLM.")
    print("Type 'quit' or 'exit' to stop.")
    print("-----------------------------")

    while not shutdown_requested:
        try:
            # Get user input asynchronously
            print(f"\n{user_name}: ", end="")
            user_input_line = await asyncio.get_event_loop().run_in_executor(
                None, sys.stdin.readline
            )
            user_input = user_input_line.strip()

            if not user_input:
                continue

            if user_input.lower() in ['quit', 'exit']:
                shutdown_requested = True
                break

            # Add user message to history
            timestamp = datetime.datetime.now()
            conversation_history.append((timestamp, 'user', user_name, user_input))

            print(f"\n{config.PERSONA_NAME} is thinking...")

            # --- Pre-fetch memory data ---
            user_profile_data = None
            related_memories_data = []
            wolf_memory_data = None

            if getattr(config, 'WOLF_MEMORY_ENABLED', False):
                print(f"[WolfMemory] Querying memory for '{user_name}'...")
                wolf_memory_data = wolf_memory_client.query_user(user_name)
                if wolf_memory_data and wolf_memory_data.get("found"):
                    print("[WolfMemory] User memory found.")
                else:
                    print("[WolfMemory] No existing memory for this user.")
            else:
                print(f"Fetching ChromaDB data for '{user_name}'...")
                user_profile_data = chroma_client.get_entity_profile(user_name)
                related_memories_data = chroma_client.get_related_memories(user_name, topic=user_input, limit=5)
                print("ChromaDB data fetch complete.")
            # --- End Pre-fetch ---

            # Call LLM interaction function, passing fetched data
            bot_response_data = await llm_interaction.get_llm_response(
                current_sender_name=user_name,
                history=list(conversation_history),
                mcp_sessions=active_mcp_sessions,
                available_mcp_tools=all_discovered_mcp_tools,
                persona_details=wolfhart_persona_details,
                user_profile=user_profile_data,
                related_memories=related_memories_data,
                wolf_memory=wolf_memory_data,
            )

            # Print the full response structure for debugging
            print("\n--- LLM Response Data ---")
            print(json.dumps(bot_response_data, indent=2, ensure_ascii=False))
            print("-------------------------")

            # Extract and print key parts
            bot_dialogue = bot_response_data.get("dialogue", "")
            thoughts = bot_response_data.get("thoughts", "")
            commands = bot_response_data.get("commands", [])
            valid_response = bot_response_data.get("valid_response", False)

            if thoughts:
                print(f"\nThoughts: {thoughts}")
            if commands:
                print(f"\nCommands:")
                for cmd in commands:
                    print(f"  - Type: {cmd.get('type')}, Params: {cmd.get('parameters')}")
            if bot_dialogue:
                print(f"\n{config.PERSONA_NAME}: {bot_dialogue}")
                if valid_response:
                    timestamp = datetime.datetime.now()
                    conversation_history.append((timestamp, 'bot', config.PERSONA_NAME, bot_dialogue))

                    # --- Wolf Memory: record interaction ---
                    if getattr(config, 'WOLF_MEMORY_ENABLED', False):
                        print("[WolfMemory] Recording interaction...")
                        wolf_memory_client.record_interaction(
                            username=user_name,
                            user_input=user_input,
                            bot_thoughts=thoughts or "",
                            bot_output=bot_dialogue,
                            timestamp=timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                        )
                        print("[WolfMemory] Interaction recorded.")
                    # --- End Wolf Memory record ---
                else:
                    print("(Note: LLM marked this dialogue as potentially invalid/incomplete)")
            else:
                print(f"\n{config.PERSONA_NAME}: (No dialogue content)")


        except (EOFError, KeyboardInterrupt):
            print("\nInterrupted. Shutting down...")
            shutdown_requested = True
            break
        except Exception as e:
            print(f"\nError during interaction: {e}")
            import traceback
            traceback.print_exc()
            # Optionally break or continue after error
            # break

    print("\nExiting debug loop.")


# --- Program Entry Point ---
if __name__ == "__main__":
    print("Starting LLM Debug Script...")
    loop = asyncio.get_event_loop()
    main_task = None
    try:
        main_task = loop.create_task(debug_loop())
        loop.run_until_complete(main_task)
    except KeyboardInterrupt:
        print("\nCtrl+C detected. Initiating shutdown...")
        shutdown_requested = True
        if main_task and not main_task.done():
             main_task.cancel()
             # Allow cancellation to propagate
             loop.run_until_complete(main_task)
    except Exception as e:
        print(f"Top-level error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Ensure shutdown runs even if loop was interrupted
        if not exit_stack.is_active: # Check if already closed
             print("Running final shutdown...")
             loop.run_until_complete(shutdown())
        loop.close()
        print("LLM Debug Script finished.")

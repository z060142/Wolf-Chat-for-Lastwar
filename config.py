# config.py
import os
import json # Import json for building args string
from dotenv import load_dotenv # Import load_dotenv

# --- Load environment variables from .env file ---
load_dotenv()
print("Attempted to load environment variables from .env file.")
# --- End Load ---

# OpenAI API Configuration / OpenAI-Compatible Provider Settings
# --- Modify these lines ---
# Leave OPENAI_API_BASE_URL as None or "" to use official OpenAI
OPENAI_API_BASE_URL = "https://openrouter.ai/api/v1"  # <--- For example "http://localhost:1234/v1" or your provider URL
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
#LLM_MODEL = "anthropic/claude-3.7-sonnet"
#LLM_MODEL = "meta-llama/llama-4-maverick"
LLM_MODEL = "deepseek/deepseek-chat-v3-0324"      # <--- Ensure this matches the model name provided by your provider

EXA_API_KEY = os.getenv("EXA_API_KEY")

# --- Dynamically build Exa server args ---
exa_config_dict = {"exaApiKey": EXA_API_KEY if EXA_API_KEY else "YOUR_EXA_KEY_MISSING"}
# Need to dump dict to JSON string, then properly escape it for cmd arg
# Using json.dumps handles internal quotes correctly.
# The outer quotes for cmd might need careful handling depending on OS / shell.
# For cmd /c on Windows, embedding escaped JSON often works like this:
exa_config_arg_string = json.dumps(json.dumps(exa_config_dict)) # Double dump for cmd escaping? Or just one? Test needed.
# Let's try single dump first, often sufficient if passed correctly by subprocess
exa_config_arg_string_single_dump = json.dumps(exa_config_dict)

# --- MCP Server Configuration ---
MCP_SERVERS = {
    "exa": {
        "command": "cmd",
        "args": [
            "/c",
            "npx",
            "-y",
            "@smithery/cli@latest",
            "run",
            "exa",
            "--config",
            # Pass the dynamically created config string with the environment variable key
            exa_config_arg_string # Use the properly escaped variable
        ],
    },
    "servers": {
      "command": "npx",
      "args": [
        "-y",
        "@smithery/cli@latest",
        "run",
        "@jlia0/servers",
        "--key",
        "09025967-c177-4653-9af4-40603a1cbd11"
      ]
    }
    # Add or remove servers as needed
}

# MCP Client Configuration
MCP_CONFIRM_TOOL_EXECUTION = False # True: Confirm before execution, False: Execute automatically

# Persona Configuration
PERSONA_NAME = "Wolfhart"
# PERSONA_RESOURCE_URI = "persona://wolfhart/details" # Now using local file instead

# Game window title (used in ui_interaction.py)
WINDOW_TITLE = "Last War-Survival Game"

# --- Print loaded keys for verification (Optional - BE CAREFUL!) ---
# print(f"DEBUG: Loaded OPENAI_API_KEY: {'*' * (len(OPENAI_API_KEY) - 4) + OPENAI_API_KEY[-4:] if OPENAI_API_KEY else 'Not Found'}")
# print(f"DEBUG: Loaded EXA_API_KEY: {'*' * (len(EXA_API_KEY) - 4) + EXA_API_KEY[-4:] if EXA_API_KEY else 'Not Found'}")
# print(f"DEBUG: Exa args: {MCP_SERVERS['exa']['args']}")
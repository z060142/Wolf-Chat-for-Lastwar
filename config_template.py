# ====================================================================
# Wolf Chat Configuration Template
# This file is used by setup.py to generate the final config.py
# ====================================================================
import os
import json
from dotenv import load_dotenv

# --- Load environment variables from .env file ---
load_dotenv()
print("Loaded environment variables from .env file.")

# =============================================================================
# OpenAI API Configuration / OpenAI-Compatible Provider Settings
# =============================================================================
# Leave OPENAI_API_BASE_URL as None or "" to use official OpenAI
OPENAI_API_BASE_URL = "${OPENAI_API_BASE_URL}"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LLM_MODEL = "${LLM_MODEL}"

# =============================================================================
# External API Keys
# =============================================================================
EXA_API_KEY = os.getenv("EXA_API_KEY")

# --- Exa Configuration ---
exa_config_dict = {"exaApiKey": EXA_API_KEY if EXA_API_KEY else "YOUR_EXA_KEY_MISSING"}
exa_config_arg_string = json.dumps(exa_config_dict)

# =============================================================================
# MCP Server Configuration
# =============================================================================
MCP_SERVERS = ${MCP_SERVERS}

# Default MCP server configurations include system prompts for each server
# These are dynamically loaded based on enabled servers in the UI
# 
# Template structure for MCP servers:
# {
#     "server_name": {
#         "command": "command_to_run",
#         "args": ["arg1", "arg2", ...],
#         "env": {"ENV_VAR": "value"},
#         "system_prompt": """
#         **SERVER CAPABILITIES:**
#         Description of what this server provides...
#         """
#     }
# }

# =============================================================================
# MCP Client Configuration
# =============================================================================
MCP_CONFIRM_TOOL_EXECUTION = False  # True: Confirm before execution, False: Execute automatically

# =============================================================================
# Chat Logging Configuration
# =============================================================================
ENABLE_CHAT_LOGGING = ${ENABLE_CHAT_LOGGING}
LOG_DIR = "${LOG_DIR}"

# =============================================================================
# Persona Configuration
# =============================================================================
PERSONA_NAME = "Wolfhart"

# =============================================================================
# Game Window Configuration
# =============================================================================
WINDOW_TITLE = "${WINDOW_TITLE}"
ENABLE_SCHEDULED_RESTART = ${ENABLE_SCHEDULED_RESTART}
RESTART_INTERVAL_MINUTES = ${RESTART_INTERVAL_MINUTES}
GAME_EXECUTABLE_PATH = r"${GAME_EXECUTABLE_PATH}"
GAME_WINDOW_X = ${GAME_WINDOW_X}
GAME_WINDOW_Y = ${GAME_WINDOW_Y}
GAME_WINDOW_WIDTH = ${GAME_WINDOW_WIDTH}
GAME_WINDOW_HEIGHT = ${GAME_WINDOW_HEIGHT}
MONITOR_INTERVAL_SECONDS = ${MONITOR_INTERVAL_SECONDS}

# =============================================================================
# Game Settings - Deduplication Configuration
# =============================================================================
DEDUPLICATION_WINDOW_SIZE = ${DEDUPLICATION_WINDOW_SIZE}  # 統一控制圖片去重和文字去重的滾動視窗大小

# =============================================================================
# ChromaDB Memory Configuration
# =============================================================================
ENABLE_PRELOAD_PROFILES = ${ENABLE_PRELOAD_PROFILES}
PRELOAD_RELATED_MEMORIES = ${PRELOAD_RELATED_MEMORIES}

# Collection Names (used for both local access and MCP tool calls)
PROFILES_COLLECTION = "${PROFILES_COLLECTION}"
CONVERSATIONS_COLLECTION = "${CONVERSATIONS_COLLECTION}"
BOT_MEMORY_COLLECTION = "${BOT_MEMORY_COLLECTION}"

# Ensure Chroma path is consistent for both direct access and MCP
CHROMA_DATA_DIR = os.path.abspath("chroma_data")

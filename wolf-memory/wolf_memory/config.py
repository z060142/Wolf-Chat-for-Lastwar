import os
from pathlib import Path

# Base paths
BASE_DIR = Path(__file__).parent.parent

# WOLF_MEMORY_DATA_DIR allows overriding the memories directory (e.g. for test mode)
_data_dir_env = os.environ.get("WOLF_MEMORY_DATA_DIR", "")
MEMORIES_DIR = Path(_data_dir_env) if _data_dir_env else BASE_DIR / "memories"

ARCHIVE_DIR = MEMORIES_DIR / "archive"
USERS_DIR = MEMORIES_DIR / "users"
INDEX_FILE = MEMORIES_DIR / "INDEX.json"
WINDOW_FILE = MEMORIES_DIR / "window.md"

# LLM backend: 'ollama' | 'requests'
LLM_BACKEND = os.environ.get("WOLF_MEMORY_BACKEND", "ollama")

# Ollama settings
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_API_KEY = os.environ.get("OLLAMA_API_KEY", "")
OLLAMA_MODEL = os.environ.get("WOLF_MEMORY_MODEL", "qwen3-coder-next:cloud")

# Memory thresholds
WINDOW_MAX_ENTRIES = 50          # Entries before archiving the window
PERSONA_UPDATE_INTERVAL = 5      # Conversations before persona refresh
COMPACT_MIN_INTERVAL_HOURS = 10 / 60  # Minimum hours between compact updates (10 minutes)

# Agent concurrency
MAX_CONCURRENT_AGENTS = 3

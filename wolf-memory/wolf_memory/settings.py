import os
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).parent.parent
MEMORIES_DIR = BASE_DIR / "memories"

# Memory layer directories
LAYERS = ["core", "episodic", "working", "knowledge"]

# Index file
INDEX_FILE = MEMORIES_DIR / "INDEX.json"

# LLM backend: 'ollama' | 'requests'
LLM_BACKEND = os.environ.get("WOLF_MEMORY_LLM_BACKEND", "ollama")

# Ollama settings
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3-coder-next:cloud")
OLLAMA_API_KEY = os.environ.get("OLLAMA_API_KEY", "")

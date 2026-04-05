from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./wolfina.db"
    debug: bool = False
    # Minimum number of distinct reviewers required before a proposal can be approved.
    min_reviewers: int = 1

    # --- API server port ---
    api_port: int = 8765

    # --- LLM provider: "ollama" or "openai" ---
    llm_provider: str = "ollama"

    # Ollama Cloud settings
    ollama_api_key: str = ""
    ollama_host: str = "https://ollama.com"
    ollama_model: str = "gpt-oss:120b"

    # OpenAI / OpenRouter settings
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o"

    # --- Conversation trigger thresholds ---
    trigger_msg_count: int = 20
    trigger_char_count: int = 2000
    trigger_duration_sec: int = 300


settings = Settings()

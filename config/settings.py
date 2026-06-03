from __future__ import annotations

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    # Model provider
    # "anthropic" | "openai" | "openrouter" | "gemini" | "grok" | "ollama" | "lm_studio"
    model_provider: str

    # Anthropic
    anthropic_api_key: str
    claude_model: str
    max_tokens: int

    # OpenAI-compatible cloud providers (openai / openrouter / gemini / grok)
    openai_api_key: str
    openai_model: str

    # Local / self-hosted OpenAI-compatible providers (ollama / lm_studio / custom)
    openai_base_url: str       # overrides provider default when set
    ollama_base_url: str       # kept for backward compat; used when provider == "ollama"
    ollama_model: str          # kept for backward compat; used when provider == "ollama"

    # Discord
    discord_token: str
    discord_allowed_guild_ids: list[int]
    discord_active_channel_ids: list[int]

    # SL bot avatar credentials
    sl_bot_firstname: str
    sl_bot_lastname: str
    sl_bot_password: str

    # SL HTTP bridge
    sl_bridge_host: str
    sl_bridge_port: int
    sl_bridge_secret: str

    # Search
    search_provider: str
    search_api_key: str

    # Rate limiting
    rate_limit_capacity: int
    rate_limit_refill_rate: float

    # Memory
    memory_dir: str
    notes_dir: str
    memory_max_history: int
    owner_sl_name: str
    owner_discord_name: str

    # Second Life
    sl_bridge_url: str
    sl_trigger_names: list[str]

    # Library system
    library_dir: str
    library_always_on_cap: int

    # Memory curator (importance scoring)
    importance_threshold: float
    importance_score_batch_size: int

    # Proactive recall: run a lightweight context-check before each message (adds one small API call)
    proactive_recall: bool


_CLOUD_OPENAI_COMPAT = {"openai", "openrouter", "gemini", "grok"}


def load_settings() -> Settings:
    model_provider = os.getenv("MODEL_PROVIDER", "anthropic").lower()

    if model_provider == "anthropic":
        anthropic_api_key = _require("ANTHROPIC_API_KEY")
    else:
        anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")

    if model_provider in _CLOUD_OPENAI_COMPAT:
        openai_api_key = _require("OPENAI_API_KEY")
    else:
        openai_api_key = os.getenv("OPENAI_API_KEY", "")

    guild_ids_raw = os.getenv("DISCORD_ALLOWED_GUILD_IDS", "").strip()
    guild_ids = (
        [int(g.strip()) for g in guild_ids_raw.split(",") if g.strip()]
        if guild_ids_raw
        else []
    )

    return Settings(
        model_provider=model_provider,
        anthropic_api_key=anthropic_api_key,
        claude_model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"),
        max_tokens=int(os.getenv("CLAUDE_MAX_TOKENS", "2048")),
        openai_api_key=openai_api_key,
        openai_model=os.getenv("OPENAI_MODEL", ""),
        openai_base_url=os.getenv("OPENAI_BASE_URL", ""),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        ollama_model=os.getenv("OLLAMA_MODEL", "llama3.2"),
        discord_token=os.getenv("DISCORD_TOKEN", ""),
        discord_allowed_guild_ids=guild_ids,
        discord_active_channel_ids=[
            int(c.strip())
            for c in os.getenv("DISCORD_ACTIVE_CHANNEL_IDS", "").split(",")
            if c.strip()
        ],
        sl_bot_firstname=os.getenv("SL_BOT_FIRSTNAME", ""),
        sl_bot_lastname=os.getenv("SL_BOT_LASTNAME", ""),
        sl_bot_password=os.getenv("SL_BOT_PASSWORD", ""),
        sl_bridge_host=os.getenv("SL_BRIDGE_HOST", "0.0.0.0"),
        sl_bridge_port=int(os.getenv("SL_BRIDGE_PORT", "8080")),
        sl_bridge_secret=os.getenv("SL_BRIDGE_SECRET", ""),
        search_provider=os.getenv("SEARCH_PROVIDER", "serper"),
        search_api_key=os.getenv("SEARCH_API_KEY", ""),
        rate_limit_capacity=int(os.getenv("RATE_LIMIT_CAPACITY", "5")),
        rate_limit_refill_rate=float(os.getenv("RATE_LIMIT_REFILL_RATE", "0.5")),
        memory_dir=os.getenv("MEMORY_DIR", "./data/memory"),
        notes_dir=os.getenv("NOTES_DIR", "./data/notes"),
        memory_max_history=int(os.getenv("MEMORY_MAX_HISTORY", "20")),
        owner_sl_name=os.getenv("OWNER_SL_NAME", ""),
        owner_discord_name=os.getenv("OWNER_DISCORD_NAME", ""),
        sl_bridge_url=os.getenv("SL_BRIDGE_URL", ""),
        sl_trigger_names=[
            t.strip() for t in os.getenv("SL_TRIGGER_NAMES", "").split(",") if t.strip()
        ],
        library_dir=os.getenv("LIBRARY_DIR", "./data/library"),
        library_always_on_cap=int(os.getenv("LIBRARY_ALWAYS_ON_CAP", "4000")),
        importance_threshold=float(os.getenv("IMPORTANCE_THRESHOLD", "0.4")),
        importance_score_batch_size=int(os.getenv("IMPORTANCE_SCORE_BATCH_SIZE", "20")),
        proactive_recall=os.getenv("PROACTIVE_RECALL", "").lower() == "true",
    )


def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(f"Required environment variable '{key}' is not set.")
    return val

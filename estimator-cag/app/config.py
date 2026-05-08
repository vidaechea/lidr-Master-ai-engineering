from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProvider = Literal["openai", "anthropic", "litellm"]

LLMModel = Literal[
    # OpenAI
    "gpt-3.5-turbo",
    "gpt-4-turbo",
    "gpt-4o-mini",
    "gpt-5.4-mini",
    "gpt-5.4",
    "o3-mini",
    "o3",
    "o4-mini",
    "o4-mini-2025-04-16",
    # Anthropic
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-6",
    "claude-opus-4-7",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    llm_provider: LLMProvider = "openai"
    llm_model: LLMModel = "gpt-4o-mini"
    app_env: str = "development"
    log_level: str = "DEBUG"
    example_fixture: Optional[Literal["short", "long"]] = None

    # LiteLLM Router failover policy
    router_num_retries: int = 2
    router_timeout: float = 30.0
    router_retry_after: int = 5
    router_allowed_fails: int = 2
    router_cooldown_time: int = 60

    # Cache
    cache_enabled: bool = False
    redis_url: str = "redis://localhost:6379"
    cache_ttl: int = 86400  # 24 hours


settings = Settings()

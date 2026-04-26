from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    app_env: str = "development"
    log_level: str = "DEBUG"

    class Config:
        env_file = ".env"


settings = Settings()

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str
    anthropic_api_key: str
    model_name: str = "gpt-4o-mini"

    class Config:
        env_file = ".env"


settings = Settings()

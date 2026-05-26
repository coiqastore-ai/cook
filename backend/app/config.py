from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://mealie:mealie@localhost:5432/mealie"
    bot_token: str = ""
    miniapp_url: str = "http://localhost:5173"
    openrouter_api_key: str = ""
    openrouter_model_fast: str = "deepseek/deepseek-chat"            # normalizer, aggregator
    openrouter_model_smart: str = "google/gemini-2.5-flash"          # recipe parser, timeline + audio
    openrouter_model_vision: str = "qwen/qwen-2.5-vl-72b-instruct"   # photo/screenshot recognition

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/calendar/oauth/callback"

    # Shared secret between bot and backend for internal API calls (bypasses initData check)
    internal_api_key: str = ""


settings = Settings()

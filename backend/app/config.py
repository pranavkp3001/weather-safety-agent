from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from pathlib import Path


class Settings(BaseSettings):
    APP_NAME: str = "MediBuddy Weather-Advisory Support Bot"
    APP_ENV: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # LLM Settings
    LLM_PROVIDER: str = "mock"  # "mock", "gemini", "openai", "anthropic"
    LLM_MODEL: str = "gemini-2.5-flash"
    GEMINI_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None

    # Weather Service Settings
    GEOCODING_API_URL: str = "https://geocoding-api.open-meteo.com/v1/search"
    FORECAST_API_URL: str = "https://api.open-meteo.com/v1/forecast"
    WEATHER_REQUEST_TIMEOUT: float = 10.0

    # Policy Path
    SOPS_FILE_PATH: str = str(Path(__file__).parent / "policies" / "sops.yaml")

    # Session Settings
    SESSION_TTL_MINUTES: int = 60

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

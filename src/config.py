from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://user:password@localhost:5432/event_scraper"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Scraper
    request_delay: float = 1.0
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

    # Google API Key (aus .env laden!)
    google_api_key: str = ""

    # Geocoding
    geocoding_dry_run: bool = False  # Wenn True: kein API-Call, nur Logging

    # CORS - kommaseparierte Origins, "*" fuer alle (nur Development)
    cors_origins: str = "*"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignoriere unbekannte Variablen aus .env




@lru_cache
def get_settings() -> Settings:
    return Settings()

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "HockeyLevelUp"
    environment: str = "local"

    database_url: str = "postgresql+asyncpg://hockey:hockey@localhost:5432/hockey_level_up"

    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    cors_origins: list[str] = ["http://localhost:5173"]
    # Lets a phone/tablet on the same Wi-Fi hit the Vite dev server at the
    # PC's LAN IP (e.g. http://192.168.1.23:5173) without opening CORS up to
    # the whole internet -- only private RFC1918 ranges on port 5173 match.
    # Set to "" in .env to disable entirely (e.g. for a locked-down prod env).
    cors_origin_regex: str = (
        r"^http://(192\.168\.\d{1,3}\.\d{1,3}"
        r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
        r"|172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}):5173$"
    )

    avatar_upload_dir: str = "static/avatars"


@lru_cache
def get_settings() -> Settings:
    return Settings()

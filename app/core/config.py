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
    # Same static_root as avatar_upload_dir (both live under "static/") --
    # already covered by the existing StaticFiles mount in main.py, no
    # separate mount needed.
    reference_article_image_upload_dir: str = "static/reference-articles"
    team_logo_upload_dir: str = "static/team-logos"

    # VAPID key pair for Web Push (RFC 8292) -- generated once via
    # py_vapid.Vapid().generate_keys(), raw EC key bytes, base64url-encoded
    # (no padding): 32-byte private scalar / 65-byte uncompressed public
    # point, the same format pywebpush's Vapid.from_string() and the
    # browser's PushManager.subscribe({applicationServerKey}) both expect.
    # Dev-only pair, same "committed, not actually secret" convention as
    # jwt_secret_key above -- regenerate before any real deployment.
    vapid_private_key: str = "fmVrz4YsbsIibjJcNvHVpUGLkDuAHvcO-2CQwsveCy0"
    vapid_public_key: str = (
        "BPD8KGVrzMDG5oZONsvz7dVBRDiE9b8IRFJdQn7BZ-Adqjz7o_U753g3zrK01JeBzBmU3NVoUJxNWPVNa1IVOXA"
    )
    # "sub" claim in the VAPID JWT -- contact address push services may use
    # if they need to reach the sender; a placeholder is normal for dev.
    vapid_subject: str = "mailto:admin@example.com"

    # AI coach chat (POST /users/me/coach-chat) -- premium-gated but stays
    # functionally off (503) until this is filled in, since a real key
    # costs money per message. Заполнить перед включением ИИ-чата.
    anthropic_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()

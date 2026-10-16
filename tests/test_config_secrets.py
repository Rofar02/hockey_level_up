"""Step 8 (security, 1): production refuses the committed dev secrets --
and (2026-10-13, А5) default service passwords, leftover placeholders and a
misspelt environment."""
import pytest
from pydantic import ValidationError

from app.core.config import DEV_JWT_SECRET_KEY, DEV_VAPID_PRIVATE_KEY, Settings

STRONG = "s" * 48
OTHER_VAPID = "another-private-key"


REAL_DB = "postgresql+asyncpg://hockey:Xq7-real-pass@postgres:5432/hockey_level_up"
REAL_MQ = "amqp://icelevel:Mq9-real-pass@rabbitmq:5672/"


def _settings(**values) -> Settings:
    return Settings(_env_file=None, **values)


def _production(**values) -> Settings:
    base = {
        "environment": "production",
        "jwt_secret_key": STRONG,
        "vapid_private_key": OTHER_VAPID,
        "database_url": REAL_DB,
        "rabbitmq_url": REAL_MQ,
    }
    return _settings(**{**base, **values})


@pytest.mark.parametrize(
    "values",
    [
        {"jwt_secret_key": DEV_JWT_SECRET_KEY, "vapid_private_key": OTHER_VAPID},
        {"jwt_secret_key": "short", "vapid_private_key": OTHER_VAPID},
        {"jwt_secret_key": STRONG, "vapid_private_key": DEV_VAPID_PRIVATE_KEY},
    ],
)
def test_production_refuses_dev_secrets(values) -> None:
    with pytest.raises(ValidationError, match="Unsafe production settings"):
        _production(**values)


def test_production_starts_with_real_secrets() -> None:
    settings = _production()
    assert settings.jwt_secret_key == STRONG


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"database_url": "postgresql+asyncpg://hockey:hockey@postgres:5432/db"}, "DATABASE_URL"),
        ({"database_url": "postgresql+asyncpg://hockey:__CHANGE_ME__@postgres:5432/db"}, "DATABASE_URL"),
        ({"rabbitmq_url": "amqp://guest:guest@rabbitmq:5672/"}, "RABBITMQ_URL"),
        ({"rabbitmq_url": "amqp://rabbitmq:5672/"}, "RABBITMQ_URL"),
        ({"resend_api_key": "__CHANGE_ME__"}, "RESEND_API_KEY"),
    ],
)
def test_production_refuses_default_passwords_and_placeholders(values, message) -> None:
    with pytest.raises(ValidationError, match=message):
        _production(**values)


def test_a_misspelt_environment_does_not_start() -> None:
    with pytest.raises(ValidationError):
        _settings(environment="prod")


def test_local_keeps_the_dev_defaults() -> None:
    settings = _settings(environment="local")
    assert settings.jwt_secret_key == DEV_JWT_SECRET_KEY

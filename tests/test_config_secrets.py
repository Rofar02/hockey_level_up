"""Step 8 (security, 1): production refuses the committed dev secrets."""
import pytest
from pydantic import ValidationError

from app.core.config import DEV_JWT_SECRET_KEY, DEV_VAPID_PRIVATE_KEY, Settings

STRONG = "s" * 48
OTHER_VAPID = "another-private-key"


def _settings(**values) -> Settings:
    return Settings(_env_file=None, **values)


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
        _settings(environment="production", **values)


def test_production_starts_with_real_secrets() -> None:
    settings = _settings(environment="production", jwt_secret_key=STRONG, vapid_private_key=OTHER_VAPID)
    assert settings.jwt_secret_key == STRONG


def test_local_keeps_the_dev_defaults() -> None:
    settings = _settings(environment="local")
    assert settings.jwt_secret_key == DEV_JWT_SECRET_KEY

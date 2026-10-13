from pydantic import BaseModel, EmailStr, Field


# 2026-10-13 (А3): repr=False on every secret-bearing field -- a model that
# lands in a log line or an exception message prints without them.


class TokenPair(BaseModel):
    access_token: str = Field(repr=False)
    refresh_token: str = Field(repr=False)
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str = Field(repr=False)


class LogoutRequest(RefreshRequest):
    # This device's Web Push endpoint, when it has one (А10): a signed-out
    # phone stops getting the player's notifications.
    push_endpoint: str | None = Field(default=None, max_length=2048, repr=False)


class DetailResponse(BaseModel):
    """Generic {"detail": "..."} body -- used by every verify-email/
    password-reset endpoint below, none of which need to return more than a
    human-readable outcome (see PasswordResetRequest's generic-response
    requirement in particular: an identical *shape* as well as identical
    content matters there)."""

    detail: str


class EmailAvailabilityRead(BaseModel):
    available: bool


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str = Field(repr=False)
    # Same bounds as UserCreate.password (app/schemas/user.py) -- a reset
    # password is still just a password, same policy applies.
    new_password: str = Field(min_length=8, max_length=128, repr=False)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128, repr=False)
    new_password: str = Field(min_length=8, max_length=128, repr=False)


class EmailVerifyConfirm(BaseModel):
    token: str = Field(repr=False)

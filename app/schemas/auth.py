from pydantic import BaseModel, EmailStr, Field


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class DetailResponse(BaseModel):
    """Generic {"detail": "..."} body -- used by every verify-email/
    password-reset endpoint below, none of which need to return more than a
    human-readable outcome (see PasswordResetRequest's generic-response
    requirement in particular: an identical *shape* as well as identical
    content matters there)."""

    detail: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    # Same bounds as UserCreate.password (app/schemas/user.py) -- a reset
    # password is still just a password, same policy applies.
    new_password: str = Field(min_length=8, max_length=128)

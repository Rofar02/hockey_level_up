from pydantic import BaseModel


class OnboardingTaskRead(BaseModel):
    id: str
    title: str
    hint: str
    xp: int
    to: str
    done: bool


class OnboardingRead(BaseModel):
    """POST /users/me/onboarding/sync -- the "Путь новичка" card."""

    visible: bool
    tasks: list[OnboardingTaskRead]
    # Paid on this sync -- the card says "+N XP" for them.
    newly_done: list[str]
    xp_awarded: int
    finish_bonus_xp: int

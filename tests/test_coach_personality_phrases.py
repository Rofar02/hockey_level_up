"""Coach-personality reminder phrase bank: every (personality, preference,
session_type) combo must resolve to a non-empty string, and GAME phrases
must always read as a game (not "тренировка X"), same invariant
reminder_scheduler's own GAME test checks against the wired-up default.
"""
from app.models.schedule import DaySessionType
from app.models.user import CoachPersonality, ReminderPreference
from app.services.coach_personality_phrases import REMINDER_PHRASES, get_reminder_body

_ALL_KEYS = [
    (preference, session_type)
    for preference in (ReminderPreference.MORNING, ReminderPreference.EVENING)
    for session_type in (DaySessionType.ON_ICE, DaySessionType.OFF_ICE, DaySessionType.GAME)
]


def test_every_personality_covers_every_reminder_combo() -> None:
    for personality in CoachPersonality:
        for key in _ALL_KEYS:
            phrases = REMINDER_PHRASES[personality][key]
            assert len(phrases) >= 1
            for phrase in phrases:
                assert phrase.strip() != ""


def test_get_reminder_body_returns_one_of_the_configured_phrases() -> None:
    for personality in CoachPersonality:
        for preference, session_type in _ALL_KEYS:
            body = get_reminder_body(personality, preference, session_type)
            assert body in REMINDER_PHRASES[personality][(preference, session_type)]


def test_game_phrases_never_reuse_training_wording() -> None:
    for personality in CoachPersonality:
        for preference in (ReminderPreference.MORNING, ReminderPreference.EVENING):
            for phrase in REMINDER_PHRASES[personality][(preference, DaySessionType.GAME)]:
                assert "тренировка" not in phrase.lower()

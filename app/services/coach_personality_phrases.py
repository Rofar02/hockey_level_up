"""Templated (non-AI) coach-voice copy for push reminders, keyed by
CoachPersonality. Deliberately separate from coach_chat_service (the real
LLM-backed "AI-тренер" feature) -- this is canned string selection only,
see CoachPersonality's docstring in app/models/user.py.

Each (preference, session_type) combo maps to a small list of interchangeable
phrases -- get_reminder_body picks one at random per send so a user with
reminders on for months doesn't see the exact same line every single time.
"""
import random

from app.models.schedule import DaySessionType
from app.models.user import CoachPersonality, ReminderPreference

_PhraseKey = tuple[ReminderPreference, DaySessionType]

REMINDER_PHRASES: dict[CoachPersonality, dict[_PhraseKey, list[str]]] = {
    CoachPersonality.CALM: {
        (ReminderPreference.MORNING, DaySessionType.ON_ICE): [
            "Сегодня тренировка на льду.",
            "Сегодня на повестке — лёд.",
        ],
        (ReminderPreference.EVENING, DaySessionType.ON_ICE): [
            "Завтра тренировка на льду.",
            "Завтра на повестке — лёд.",
        ],
        (ReminderPreference.MORNING, DaySessionType.OFF_ICE): [
            "Сегодня тренировка в зале.",
            "Сегодня на повестке — зал.",
        ],
        (ReminderPreference.EVENING, DaySessionType.OFF_ICE): [
            "Завтра тренировка в зале.",
            "Завтра на повестке — зал.",
        ],
        (ReminderPreference.MORNING, DaySessionType.GAME): [
            "Сегодня игра — не забудьте про разминку и настрой.",
            "Сегодня игра. Разминка и настрой — по плану.",
        ],
        (ReminderPreference.EVENING, DaySessionType.GAME): [
            "Завтра игра — не забудьте про разминку и настрой.",
            "Завтра игра. Разминка и настрой — по плану.",
        ],
    },
    CoachPersonality.STRICT: {
        (ReminderPreference.MORNING, DaySessionType.ON_ICE): [
            "Сегодня лёд. Опозданий не будет.",
            "Тренировка на льду сегодня. Без пропусков.",
        ],
        (ReminderPreference.EVENING, DaySessionType.ON_ICE): [
            "Завтра лёд. Ляг спать вовремя.",
            "Завтра тренировка на льду. Готовность обязательна.",
        ],
        (ReminderPreference.MORNING, DaySessionType.OFF_ICE): [
            "Сегодня зал. Дисциплина решает всё.",
            "Тренировка в зале сегодня. Пропускать нельзя.",
        ],
        (ReminderPreference.EVENING, DaySessionType.OFF_ICE): [
            "Завтра зал. Никаких отговорок.",
            "Завтра тренировка в зале. Будь готов.",
        ],
        (ReminderPreference.MORNING, DaySessionType.GAME): [
            "Сегодня игра. Разминка полностью, без сокращений.",
            "Игра сегодня. Настрой — как на бой.",
        ],
        (ReminderPreference.EVENING, DaySessionType.GAME): [
            "Завтра игра. Отдых сегодня — тоже часть подготовки.",
            "Завтра игра. Голова должна быть готова уже сейчас.",
        ],
    },
    CoachPersonality.HUMOR: {
        (ReminderPreference.MORNING, DaySessionType.ON_ICE): [
            "Сегодня лёд. Коньки точили или опять на морально-волевых поедешь?",
            "Лёд сегодня. Шнурки завязать не забудь, звезда.",
        ],
        (ReminderPreference.EVENING, DaySessionType.ON_ICE): [
            "Завтра лёд. Сериальчик подождёт — ноги нужны свежие.",
            "Завтра на лёд. Ты главное выспись, остальное приложится.",
        ],
        (ReminderPreference.MORNING, DaySessionType.OFF_ICE): [
            "Сегодня зал. Отговорки сдай на входе вместе с курткой.",
            "Зал сегодня. Готовься — сегодня штанга, а не тапками по татами.",
        ],
        (ReminderPreference.EVENING, DaySessionType.OFF_ICE): [
            "Завтра зал. Заранее скажу: болеть будет — терпи.",
            "Завтра качалка. Оправдания готовь заранее — не сработают, но повеселимся.",
        ],
        (ReminderPreference.MORNING, DaySessionType.GAME): [
            "Сегодня игра. Разминка — святое, а не как обычно для галочки.",
            "Игра сегодня. Не первая, а мандражируешь как в первой — разомнись как следует.",
        ],
        (ReminderPreference.EVENING, DaySessionType.GAME): [
            "Завтра игра. Сегодня спать, а не ленту до трёх ночи листать.",
            "Завтра матч. Настрой готовь сейчас — завтра будет некогда.",
        ],
    },
    CoachPersonality.VIBE: {
        (ReminderPreference.MORNING, DaySessionType.ON_ICE): [
            "Го, сегодня лёд. Погнали, будет огонь.",
            "Сегодня катка. Настроение подтягивай, тело само подтянется.",
        ],
        (ReminderPreference.EVENING, DaySessionType.ON_ICE): [
            "Завтра лёд, бро. Ляг сегодня пораньше, скажешь спасибо.",
            "Завтра каток. Отдохни сегодня по-человечески.",
        ],
        (ReminderPreference.MORNING, DaySessionType.OFF_ICE): [
            "Сегодня качалка. Полегоньку, но без филонки.",
            "Зал сегодня. Погнали качать базу, красава.",
        ],
        (ReminderPreference.EVENING, DaySessionType.OFF_ICE): [
            "Завтра зал, дружище. Сегодня просто отдыхай.",
            "Завтра качалка. Заряжайся — завтра погнали.",
        ],
        (ReminderPreference.MORNING, DaySessionType.GAME): [
            "Сегодня игра! Разомнись как следует, и всё будет ровно.",
            "Игра сегодня, красава. Соберись, разомнись — и вперёд.",
        ],
        (ReminderPreference.EVENING, DaySessionType.GAME): [
            "Завтра игра. Сегодня отдых, голову проветри.",
            "Завтра матч, бро. Ляг пораньше — завтра нужен свежим.",
        ],
    },
}


def get_reminder_body(
    personality: CoachPersonality, preference: ReminderPreference, session_type: DaySessionType
) -> str:
    phrases = REMINDER_PHRASES[personality][(preference, session_type)]
    return random.choice(phrases)

"""The fixed list of amateur leagues a team can pick (2026-10-09).

Kept as config rather than a DB enum: a team stores only the codes
(Team.league_code / Team.division_code), so adding a league here needs no
migration. "other" carries the team's own text in Team.league_other_name --
the admin list of those texts (TeamService.list_other_league_names) shows
which ones are popular enough to add here.
"""

from dataclasses import dataclass, field

LEAGUE_NONE = "none"
LEAGUE_OTHER = "other"


@dataclass(frozen=True)
class Division:
    code: str
    name: str


@dataclass(frozen=True)
class League:
    code: str
    name: str
    divisions: tuple[Division, ...] = field(default_factory=tuple)


LEAGUES: tuple[League, ...] = (
    League(LEAGUE_NONE, "Без лиги"),
    League(
        "nhl",
        "Ночная хоккейная лига",
        divisions=(
            Division("dream", "Лига Мечты"),
            Division("hope", "Лига Надежды"),
            Division("amateur_40", "Любитель 40+"),
            Division("amateur_50", "Любитель 50+"),
        ),
    ),
    League("shl", "Студенческая хоккейная лига"),
    League(LEAGUE_OTHER, "Другая лига"),
)

LEAGUES_BY_CODE: dict[str, League] = {league.code: league for league in LEAGUES}

# Ranking inside a league and city is shown only when there is real
# competition -- a "1 из 1" place says nothing.
MIN_TEAMS_FOR_LEAGUE_RANK = 3


def league_display_name(league_code: str, other_name: str | None) -> str | None:
    """What the team card prints: None for "без лиги", the team's own text
    for "другая"."""
    if league_code == LEAGUE_NONE:
        return None
    if league_code == LEAGUE_OTHER:
        return other_name
    league = LEAGUES_BY_CODE.get(league_code)
    return league.name if league is not None else None


def division_display_name(league_code: str, division_code: str | None) -> str | None:
    league = LEAGUES_BY_CODE.get(league_code)
    if league is None or division_code is None:
        return None
    return next((d.name for d in league.divisions if d.code == division_code), None)


def normalize_text(value: str | None) -> str | None:
    """Trim and collapse inner whitespace; blank becomes None."""
    if value is None:
        return None
    collapsed = " ".join(value.split())
    return collapsed or None


def ranking_group_key(
    league_code: str, other_name: str | None, city: str | None, division_code: str | None = None
) -> tuple[str, str, str, str] | None:
    """Teams compete for a place only with teams of the same league and the
    same division (a division is its own level -- owner's call 2026-10-10)
    in the same city, compared case-insensitively ("москва" == "Москва") --
    done in Python, not SQL lower(), which depends on the database
    collation for Cyrillic. No city -> no place at all."""
    if city is None:
        return None
    other = (other_name or "").casefold() if league_code == LEAGUE_OTHER else ""
    return (league_code, other, division_code or "", city.casefold())

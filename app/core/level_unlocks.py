"""Single registry for every level-gated perk in the game (2026-08-30
gamification pass, item 6 of the roadmap) -- one place to look up "what
does level N unlock", instead of the level check for each perk living
wherever that perk's own feature happens to be implemented.

Supersedes the older, differently-tuned skill-slot tiers that used to live
in app/core/skill_preferences.py (3/6/9 at levels 8/15/25, uncapped past
that) -- this pass retunes them to a hard-capped 3/4/5/6 at levels
1/5/10/15, per an explicit product call when the two were found to
disagree (the roadmap item was written before the old tiers shipped and
never reconciled against them).

Not every perk this roadmap item originally listed is represented here --
"advanced/top technique tier" and "expanded coach lines" (levels 5/20)
would need a technique-content tiering system that doesn't exist yet and
wasn't specified in enough detail to invent one now; deliberately left out
rather than faked. Coach-personality choice stays free at every level (a
separate product call, since Settings already ships it unlocked for
everyone) -- only the skill-slot/avatar/jersey perks below are real.
"""

# Skill preference ("priority skill") slots -- how many of the ~11 skills a
# player can mark as a training priority at once. Ascending on the
# threshold; the first row whose threshold is > level wins, same pattern as
# every other tiered gate in app/core (max_difficulty_for_level,
# max_difficulty_for_stat).
_SKILL_SLOT_TIERS: list[tuple[int, int]] = [
    (5, 3),  # level < 5  -> 3 slots
    (10, 4),  # 5 <= level < 10  -> 4 slots
    (15, 5),  # 10 <= level < 15 -> 5 slots
]
SKILL_SLOT_CAP = 6  # level >= 15 -> 6 slots, hard ceiling (no further growth)

LEVEL_AVATAR_RING_CHOICE = 10
LEVEL_JERSEY_COLOR_CHOICE = 15


def max_skill_slots_for_level(level: int) -> int:
    for threshold, cap in _SKILL_SLOT_TIERS:
        if level < threshold:
            return cap
    return SKILL_SLOT_CAP


def has_avatar_ring_choice(level: int) -> bool:
    return level >= LEVEL_AVATAR_RING_CHOICE


def has_jersey_color_choice(level: int) -> bool:
    return level >= LEVEL_JERSEY_COLOR_CHOICE

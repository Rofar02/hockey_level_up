"""Rest-between-sets formula, computed on read (not a stored Exercise
column): driven by how close to a rep max the working set is, not by
periodization block phase -- low-rep near-max work needs 2-3+ minutes for
the next set to be safe and effective regardless of which week of the
block it falls in, while high-rep endurance work recovers in well under a
minute.
"""
_LOW_REPS_CEILING = 5
_LOW_REPS_REST_SECONDS = 180

_MEDIUM_REPS_CEILING = 12
_MEDIUM_REPS_REST_SECONDS = 90

_HIGH_REPS_REST_SECONDS = 45


def rest_seconds_for(target_sets: int | None, target_reps: int | None) -> int | None:
    """None whenever there's nothing to rest *between*: no sets structure at
    all (target_sets is None), or a duration-based exercise with no rep
    count -- this formula's three tiers are keyed on target_reps alone, so
    a duration-only exercise (a plank hold, a timed sprint) isn't covered
    and deliberately gets no suggested rest rather than a guessed one.

    Takes the two raw values rather than an Exercise/ExerciseRead so it
    works the same from either -- the ORM model and the read schema are
    different classes that happen to share these two field names.
    """
    if target_sets is None or target_reps is None:
        return None
    if target_reps <= _LOW_REPS_CEILING:
        return _LOW_REPS_REST_SECONDS
    if target_reps <= _MEDIUM_REPS_CEILING:
        return _MEDIUM_REPS_REST_SECONDS
    return _HIGH_REPS_REST_SECONDS

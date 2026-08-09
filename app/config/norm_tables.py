# Static fitness-test norm tables (age-adjusted score thresholds), not a DB
# table: these are curated reference values, not user data, and don't change
# at runtime.

NORM_TABLES: dict[str, dict[str, list[tuple[int, float]]]] = {
    "long_jump_cm": {
        "18-29": [(20, 150), (50, 200), (80, 230), (100, 260)],
        "30-39": [(20, 145), (50, 190), (80, 220), (100, 250)],
        "40-49": [(20, 135), (50, 175), (80, 205), (100, 235)],
        "50+": [(20, 120), (50, 160), (80, 185), (100, 210)],
    },
    "pushups_reps": {
        "18-29": [(20, 10), (50, 25), (80, 40), (100, 55)],
        "30-39": [(20, 8), (50, 20), (80, 35), (100, 50)],
        "40-49": [(20, 6), (50, 15), (80, 28), (100, 40)],
        "50+": [(20, 5), (50, 10), (80, 20), (100, 30)],
    },
    "squats_reps": {
        "18-29": [(20, 15), (50, 35), (80, 50), (100, 65)],
        "30-39": [(20, 12), (50, 30), (80, 45), (100, 58)],
        "40-49": [(20, 10), (50, 25), (80, 38), (100, 50)],
        "50+": [(20, 8), (50, 20), (80, 30), (100, 40)],
    },
    "plank_seconds": {
        "18-29": [(20, 20), (50, 60), (80, 120), (100, 180)],
        "30-39": [(20, 15), (50, 50), (80, 100), (100, 150)],
        "40-49": [(20, 10), (50, 40), (80, 80), (100, 120)],
        "50+": [(20, 10), (50, 30), (80, 60), (100, 90)],
    },
    # Lower time = better performance = higher score, unlike the other four
    # tests. See INVERSE_TESTS / score_from_value.
    "run_1km_seconds": {
        "18-29": [(20, 390), (50, 300), (80, 255), (100, 220)],
        "30-39": [(20, 405), (50, 315), (80, 270), (100, 235)],
        "40-49": [(20, 435), (50, 345), (80, 300), (100, 260)],
        "50+": [(20, 465), (50, 375), (80, 330), (100, 290)],
    },
    # -- On-ice tests below: PRELIMINARY norms, not sourced from any real
    # dataset or coaching standard -- there was no existing on-ice norm
    # table to calibrate against (unlike the 5 off-ice tests above, which
    # were already in place). These are rough, conservative estimates for
    # an amateur/recreational adult hockey player and MUST be recalibrated
    # against real timed-test data before being trusted for anything beyond
    # a placeholder starting value. Anchor points follow the same
    # (score, raw_value) shape as the off-ice tables above.
    #
    # on_ice_skating_seconds: 20m forward skate sprint from a stationary
    # start, timed to the line.
    "on_ice_skating_seconds": {
        "18-29": [(20, 6.5), (50, 5.0), (80, 4.0), (100, 3.4)],
        "30-39": [(20, 6.8), (50, 5.3), (80, 4.3), (100, 3.7)],
        "40-49": [(20, 7.2), (50, 5.7), (80, 4.7), (100, 4.1)],
        "50+": [(20, 7.8), (50, 6.2), (80, 5.2), (100, 4.6)],
    },
    # puck_handling_seconds: slalom with a puck through ~6-8 cones over a
    # ~20m course, timed start to finish.
    "puck_handling_seconds": {
        "18-29": [(20, 22.0), (50, 16.0), (80, 12.0), (100, 9.5)],
        "30-39": [(20, 23.5), (50, 17.5), (80, 13.0), (100, 10.5)],
        "40-49": [(20, 25.0), (50, 19.0), (80, 14.5), (100, 12.0)],
        "50+": [(20, 27.0), (50, 21.0), (80, 16.5), (100, 14.0)],
    },
}

INVERSE_TESTS = {"run_1km_seconds", "on_ice_skating_seconds", "puck_handling_seconds"}


def age_group(age: int) -> str:
    if age < 30:
        return "18-29"
    if age < 40:
        return "30-39"
    if age < 50:
        return "40-49"
    return "50+"


def _interpolate_linear(x: float, xs: list[float], ys: list[float]) -> float:
    """Piecewise-linear interpolation over ascending xs; extrapolates past the ends."""
    if x <= xs[0]:
        i = 0
    elif x >= xs[-1]:
        i = len(xs) - 2
    else:
        i = next(k for k in range(len(xs) - 1) if xs[k] <= x <= xs[k + 1])

    x0, x1 = xs[i], xs[i + 1]
    y0, y1 = ys[i], ys[i + 1]
    return y0 + (x - x0) * (y1 - y0) / (x1 - x0)


def score_from_value(test_name: str, age: int, raw_value: float) -> int:
    points = sorted(NORM_TABLES[test_name][age_group(age)], key=lambda p: p[0])
    scores = [p[0] for p in points]
    values = [p[1] for p in points]

    if test_name in INVERSE_TESTS:
        # Score rises as raw_value falls, so the value sequence descends
        # while xs must be ascending for the interpolation helper. Negating
        # both sides flips the axis without touching the score mapping.
        raw_score = _interpolate_linear(-raw_value, [-v for v in values], scores)
    else:
        raw_score = _interpolate_linear(raw_value, values, scores)

    return round(min(100.0, max(0.0, raw_score)))

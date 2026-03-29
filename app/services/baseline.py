"""Weighted 7-day moving average baseline (README Phase 1) — used for income loss detection."""

import json

WEIGHTS = [0.10, 0.10, 0.12, 0.13, 0.15, 0.18, 0.22]


def weighted_baseline(earnings_json: str) -> float:
    try:
        arr = [float(x) for x in json.loads(earnings_json)]
    except (json.JSONDecodeError, TypeError, ValueError):
        arr = [800.0] * 7
    if len(arr) < 7:
        arr = (arr + [800.0] * 7)[:7]
    return sum(w * e for w, e in zip(WEIGHTS, arr[-7:]))


def simulate_today_earning(baseline: float, disruption_active: bool) -> float:
    """Demo: under disruption, partner earns far less."""
    if disruption_active:
        return round(baseline * 0.18, 2)
    return baseline


def income_drop_pct(baseline: float, actual: float) -> float:
    if baseline <= 0:
        return 0.0
    return max(0.0, (baseline - actual) / baseline)

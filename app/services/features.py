"""Derive ML feature vector for premium pricing (hyper-local risk)."""

import json
import random
from app.models.user import User


def zone_derived_features(zone_id: str) -> dict[str, float]:
    """Deterministic pseudo-features from zone string (demo when no GIS DB)."""
    h = abs(hash(zone_id)) % 10000
    random.seed(h)
    return {
        "zone_flood_risk_score": round(random.uniform(0.1, 0.95), 4),
        "zone_heat_index": round(random.uniform(32.0, 42.0), 2),
        "zone_aqi_percentile": round(random.uniform(40.0, 95.0), 2),
        "disruption_frequency_local": round(random.uniform(0.0, 8.0), 2),
    }


def worker_features(user: User) -> dict[str, float]:
    try:
        arr = json.loads(user.earnings_json)
        earnings = [float(x) for x in arr]
    except (json.JSONDecodeError, TypeError, ValueError):
        earnings = [800.0] * 7
    if len(earnings) < 2:
        earnings = [800.0] * 7
    mean_e = sum(earnings) / len(earnings)
    var = sum((x - mean_e) ** 2 for x in earnings) / len(earnings)
    std = var**0.5
    worker_income_cv = round(std / mean_e if mean_e else 0.1, 4)
    expected_hours = user.avg_hours_per_day * 6
    consistency = min(1.0, user.avg_hours_per_day / 10.0)
    return {
        "worker_income_cv": worker_income_cv,
        "worker_consistency_score": round(consistency, 4),
    }


def build_feature_row(user: User) -> list[float]:
    z = zone_derived_features(user.zone_id)
    w = worker_features(user)
    merged = {**z, **w}
    return [
        merged["zone_flood_risk_score"],
        merged["zone_heat_index"],
        merged["zone_aqi_percentile"],
        merged["worker_income_cv"],
        merged["worker_consistency_score"],
        merged["disruption_frequency_local"],
    ]


def feature_dict(user: User) -> dict[str, float]:
    z = zone_derived_features(user.zone_id)
    w = worker_features(user)
    return {**z, **w}

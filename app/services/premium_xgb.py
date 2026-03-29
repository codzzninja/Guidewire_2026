"""XGBoost dynamic weekly premium adjustment."""

from pathlib import Path

import joblib
import numpy as np

from app.models.user import User
from app.services.features import build_feature_row, feature_dict

FEATURE_ORDER = [
    "zone_flood_risk_score",
    "zone_heat_index",
    "zone_aqi_percentile",
    "worker_income_cv",
    "worker_consistency_score",
    "disruption_frequency_local",
]

PLAN_BASE = {"basic": 20.0, "standard": 35.0, "pro": 50.0}
PLAN_COVERAGE = {
    "basic": (1000.0, 300.0),
    "standard": (1500.0, 500.0),
    "pro": (2500.0, 800.0),
}

_MODEL = None
_MODEL_PATH = Path(__file__).resolve().parent.parent / "ml" / "premium_xgb.pkl"


def _load_model():
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    if _MODEL_PATH.exists():
        _MODEL = joblib.load(_MODEL_PATH)
    else:
        _MODEL = None
    return _MODEL


def heuristic_adjustment(features: list[float]) -> float:
    """Fallback when model file missing: monotonic-ish adjustment from README story."""
    flood, heat, aqi, cv, consistency, disrupt = features
    adj = 0.0
    adj += (flood - 0.3) * 15
    adj += (heat - 36) * 0.8
    adj += (aqi - 60) * 0.05
    adj += cv * 40
    adj -= (consistency - 0.7) * 10
    adj += disrupt * 0.5
    return float(np.clip(adj, -8.0, 22.0))


def predict_risk_adjustment(user: User) -> tuple[float, dict]:
    row = build_feature_row(user)
    model = _load_model()
    if model is not None:
        X = np.array([row])
        adj = float(model.predict(X)[0])
        adj = float(np.clip(adj, -10.0, 25.0))
    else:
        adj = heuristic_adjustment(row)
    meta = feature_dict(user)
    meta["model_used"] = "xgboost" if model is not None else "heuristic_fallback"
    return adj, meta


def quote_plan(user: User, plan_type: str) -> dict:
    if plan_type not in PLAN_BASE:
        raise ValueError("Invalid plan")
    base = PLAN_BASE[plan_type]
    max_cov, max_event = PLAN_COVERAGE[plan_type]
    adj, feat = predict_risk_adjustment(user)
    final = round(base + adj, 2)
    final = max(5.0, final)
    return {
        "plan_type": plan_type,
        "base_weekly_premium": base,
        "risk_adjustment": round(adj, 2),
        "final_weekly_premium": final,
        "max_weekly_coverage": max_cov,
        "max_per_event": max_event,
        "feature_snapshot": feat,
    }

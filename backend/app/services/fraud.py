"""
Fraud + adversarial GPS defense (Phase 2).

- Layer 1: geographic zone vs claimed work area
- Layer 2: duplicate paid claim per event
- Layer 3: Isolation Forest on engineered features (README §7.3 / §10)
- Layer 4: Multi-Signal Trust Score (MSTS) — movement, noise, teleport, swarm (README §18)
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
from sklearn.ensemble import IsolationForest
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.data.work_zones import ZONE_BY_ID, ZONE_MATCH_RADIUS_KM
from app.models.claim import Claim
from app.models.user import User

# --- Isolation Forest: trained on synthetic in-distribution gig-worker feature vectors ---
_rng = np.random.RandomState(42)
_N = 4000
# [dist_norm, static_sig, teleport_sig, acc_noise_norm, income_drop, swarm, stale_attest, no_trace]
_X_train = np.column_stack(
    [
        _rng.uniform(0.0, 0.35, _N),
        _rng.uniform(0.0, 0.35, _N),
        _rng.uniform(0.0, 0.25, _N),
        _rng.uniform(0.15, 0.95, _N),
        _rng.uniform(0.42, 0.92, _N),
        _rng.uniform(0.0, 0.12, _N),
        _rng.uniform(0.0, 0.35, _N),
        _rng.uniform(0.0, 0.25, _N),
    ]
)
_ISO = IsolationForest(contamination=0.07, random_state=42, n_estimators=200)
_ISO.fit(_X_train)


@dataclass
class FraudResult:
    score: float
    notes: str
    approved: bool
    msts: dict[str, Any]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def coords_match_claimed_zone(lat: float, lon: float, zone_id: str) -> tuple[bool, float]:
    z = ZONE_BY_ID.get(zone_id)
    if not z:
        return False, 999.0
    d = haversine_km(lat, lon, z["lat"], z["lon"])
    return d <= ZONE_MATCH_RADIUS_KM, d


def duplicate_event(db: Session, user_id: int, event_id: str) -> bool:
    exists = (
        db.query(Claim)
        .filter(Claim.user_id == user_id, Claim.event_id == event_id, Claim.status == "paid")
        .first()
    )
    return exists is not None


def _parse_attestation(user: User) -> dict[str, Any]:
    try:
        return json.loads(user.gps_attestation_json or "{}")
    except json.JSONDecodeError:
        return {}


def _analyze_trace(samples: list[dict[str, Any]]) -> dict[str, float]:
    """Derive anti-spoofing signals from time-ordered GPS samples."""
    out: dict[str, float] = {
        "n": float(len(samples)),
        "static_score": 0.0,
        "teleport_score": 0.0,
        "accuracy_std": 0.0,
        "accuracy_mean": 0.0,
        "max_speed_kmh": 0.0,
        "duration_sec": 0.0,
    }
    if len(samples) < 2:
        return out

    accs = [float(s.get("accuracy") or 30.0) for s in samples]
    out["accuracy_mean"] = float(np.mean(accs))
    out["accuracy_std"] = float(np.std(accs)) if len(accs) > 1 else 0.0

    lats = [float(s["lat"]) for s in samples]
    lons = [float(s["lon"]) for s in samples]
    first_lat, first_lon = lats[0], lons[0]
    static_count = sum(
        1
        for la, lo in zip(lats, lons)
        if haversine_km(la, lo, first_lat, first_lon) < 0.012
    )
    out["static_score"] = min(1.0, static_count / max(len(samples), 1))

    ts0 = int(samples[0].get("ts") or 0)
    ts1 = int(samples[-1].get("ts") or 0)
    out["duration_sec"] = max(0.0, (ts1 - ts0) / 1000.0)

    max_speed = 0.0
    teleport_hits = 0
    for i in range(1, len(samples)):
        t0, t1 = int(samples[i - 1].get("ts") or 0), int(samples[i].get("ts") or 0)
        dt = max(0.001, (t1 - t0) / 1000.0)
        d_km = haversine_km(
            float(samples[i - 1]["lat"]),
            float(samples[i - 1]["lon"]),
            float(samples[i]["lat"]),
            float(samples[i]["lon"]),
        )
        v_kmh = (d_km / dt) * 3600.0
        max_speed = max(max_speed, v_kmh)
        # Urban delivery — sustained > 180 km/h between fixes is not credible
        if v_kmh > 180:
            teleport_hits += 1

    out["max_speed_kmh"] = max_speed
    out["teleport_score"] = min(1.0, teleport_hits / max(len(samples) - 1, 1))
    return out


def _swarm_coordinated_risk(db: Session, zone_id: str) -> float:
    """Elevated risk when many paid claims hit the same zone in a short window (rings)."""
    since = datetime.now(timezone.utc) - timedelta(hours=2)
    n = (
        db.query(func.count(Claim.id))
        .join(User, Claim.user_id == User.id)
        .filter(
            User.zone_id == zone_id,
            Claim.status == "paid",
            Claim.created_at >= since,
        )
        .scalar()
    ) or 0
    if n <= 12:
        return 0.0
    return min(0.22, (n - 12) * 0.015)


def _isolation_fraud_vector(v: np.ndarray) -> float:
    """Map IsolationForest decision to 0..1 higher = riskier."""
    raw = float(_ISO.decision_function(v.reshape(1, -1))[0])
    # Typical raw in [-0.2, 0.25] for IF; lower => more anomalous
    return float(np.clip(0.55 - raw * 1.9, 0.0, 1.0))


def evaluate_claim(
    db: Session,
    user: User,
    event_zone_id: str,
    event_id: str,
    income_drop_pct: float,
) -> FraudResult:
    notes: list[str] = []
    msts: dict[str, Any] = {}

    ok_zone, dist_km = coords_match_claimed_zone(user.lat, user.lon, event_zone_id)
    if not ok_zone:
        notes.append(f"GPS outside claimed work zone (~{dist_km:.1f} km from centroid)")
        msts.update({"zone_distance_km": dist_km, "layer": "geo_gate"})
        return FraudResult(
            score=0.96,
            notes="; ".join(notes),
            approved=False,
            msts=msts,
        )

    if duplicate_event(db, user.id, event_id):
        notes.append("Duplicate payout for same event")
        return FraudResult(score=0.93, notes="; ".join(notes), approved=False, msts={"layer": "duplicate"})

    att = _parse_attestation(user)
    samples = att.get("samples") if isinstance(att.get("samples"), list) else []
    trace = _analyze_trace(samples) if samples else {}

    # Staleness: stale attestation reduces trust (README: continuous validation)
    stale_penalty = 0.0
    captured_iso = att.get("captured_at")
    if isinstance(captured_iso, str):
        try:
            cap = datetime.fromisoformat(captured_iso.replace("Z", "+00:00"))
            if cap.tzinfo is None:
                cap = cap.replace(tzinfo=timezone.utc)
            age_h = (datetime.now(timezone.utc) - cap).total_seconds() / 3600.0
            if age_h > 72:
                stale_penalty = min(0.18, (age_h - 72) / 500.0)
                notes.append("GPS attestation stale — elevated review")
        except ValueError:
            stale_penalty = 0.08

    no_live_trace = len(samples) < 3
    if no_live_trace:
        stale_penalty += 0.12
        notes.append("No recent multi-point GPS trace — MSTS partially blind")

    static_score = float(trace.get("static_score", 0.0))
    teleport_score = float(trace.get("teleport_score", 0.0))
    max_speed = float(trace.get("max_speed_kmh", 0.0))
    acc_std = float(trace.get("accuracy_std", 0.0))
    acc_mean = float(trace.get("accuracy_mean", 25.0))

    # Too-clean accuracy (spoof apps often report 3–5m repeatedly)
    noise_anomaly = 0.0
    if len(samples) >= 4 and acc_std < 1.5 and acc_mean < 8.0:
        noise_anomaly = 0.22
        notes.append("GPS accuracy unnaturally stable — possible spoof")

    if max_speed > 240:
        notes.append("Impossible movement speed between fixes — blocked")
        return FraudResult(
            score=0.94,
            notes="; ".join(notes),
            approved=False,
            msts={**trace, "max_speed_kmh": max_speed, "layer": "teleport"},
        )

    if static_score > 0.92 and len(samples) >= 8:
        notes.append("Movement trace static — spoof pattern risk")
        static_score = min(1.0, static_score + 0.05)

    dist_norm = min(1.0, dist_km / max(ZONE_MATCH_RADIUS_KM, 1.0))
    acc_noise_norm = min(1.0, acc_std / 45.0) if acc_std > 0 else 0.35
    swarm = _swarm_coordinated_risk(db, user.zone_id)

    feat = np.array(
        [
            dist_norm,
            min(1.0, static_score + noise_anomaly * 0.5),
            min(1.0, teleport_score + (0.15 if max_speed > 120 else 0.0)),
            acc_noise_norm,
            income_drop_pct,
            swarm,
            min(1.0, stale_penalty * 3.5),
            0.35 if no_live_trace else 0.08,
        ],
        dtype=np.float64,
    )

    if_score = _isolation_fraud_vector(feat)
    rule_score = (
        0.18 * static_score
        + 0.28 * teleport_score
        + 0.12 * swarm
        + 0.15 * stale_penalty
        + 0.12 * noise_anomaly
        + (0.14 if no_live_trace else 0.0)
    )
    if income_drop_pct < 0.4:
        rule_score += 0.12
        notes.append("Income drop below threshold (possible inactivity)")

    combined = 0.55 * if_score + 0.45 * min(1.0, rule_score)
    if income_drop_pct > 0.88:
        combined += 0.08
        notes.append("Extreme drop — elevated review")

    combined = float(min(0.99, max(0.08, combined)))
    approved = combined < 0.75

    if income_drop_pct >= 0.4:
        notes.append("Income drop consistent with disruption")

    msts = {
        "zone_distance_km": dist_km,
        "isolation_forest_risk": round(if_score, 4),
        "rule_risk": round(rule_score, 4),
        "swarm_risk": round(swarm, 4),
        "static_score": round(static_score, 4),
        "teleport_score": round(teleport_score, 4),
        "accuracy_std_m": round(acc_std, 3),
        "samples": int(len(samples)),
        "stale_penalty": round(stale_penalty, 4),
    }

    return FraudResult(
        score=combined,
        notes="; ".join(n for n in notes if n),
        approved=approved,
        msts=msts,
    )

"""
Parametric trigger evaluation — dual gate: external disruption + income drop.
Builds 3–5 automated triggers via weather APIs + mocks.
"""

from datetime import date
import json
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.claim import Claim
from app.models.event import DisruptionEvent
from app.models.policy import Policy, PolicyStatus
from app.models.user import User
from app.services.baseline import income_drop_pct, simulate_today_earning, weighted_baseline
from app.services.fraud import evaluate_claim
from app.services.payouts import initiate_payout
from app.services.weather import fetch_all_triggers


def _social_triggers_mock() -> tuple[bool, bool]:
    """Triggers 4–5: RSS / traffic APIs in prod; deterministic calendar mock for demo."""
    d = date.today().toordinal()
    curfew = (d % 11) == 0
    zone_close = (d % 13) == 1
    return curfew, zone_close


async def evaluate_external_triggers(lat: float, lon: float, force_mock: bool) -> dict[str, Any]:
    flags: dict[str, bool] = {}
    details: dict[str, Any] = {}
    if force_mock:
        flags["heavy_rain"] = True
        flags["extreme_heat"] = False
        flags["severe_aqi"] = False
        flags["curfew_social"] = True
        flags["traffic_zone_closure"] = False
        details["mode"] = "forced_mock_disruption"
        return {"any_external": True, "flags": flags, "details": details}

    env = await fetch_all_triggers(lat, lon)
    w = env["weather"]
    a = env["aqi"]
    curfew, zone_close = _social_triggers_mock()
    flags["heavy_rain"] = bool(w["rain_trigger"])
    flags["extreme_heat"] = bool(w["heat_trigger"])
    flags["severe_aqi"] = bool(a["severe_pollution"])
    flags["curfew_social"] = curfew
    flags["traffic_zone_closure"] = zone_close
    details["weather_api"] = w
    details["aqi_api"] = a
    any_external = any(flags.values())
    return {"any_external": any_external, "flags": flags, "details": details}


def payout_formula(income_loss: float, max_per_event: float) -> float:
    return round(min(income_loss * 0.85, max_per_event), 2)


async def run_pipeline_for_user(
    db: Session,
    user: User,
    force_mock_disruption: bool = False,
) -> dict[str, Any]:
    ext = await evaluate_external_triggers(user.lat, user.lon, force_mock_disruption)
    baseline = weighted_baseline(user.earnings_json)
    disruption_active = ext["any_external"]
    today_earn = simulate_today_earning(baseline, disruption_active)
    drop = income_drop_pct(baseline, today_earn)

    gate1 = disruption_active
    gate2 = drop > 0.40

    policy = (
        db.query(Policy)
        .filter(
            Policy.user_id == user.id,
            Policy.status == PolicyStatus.active.value,
        )
        .order_by(Policy.id.desc())
        .first()
    )

    result: dict[str, Any] = {
        "user_id": user.id,
        "external": ext,
        "baseline_daily": round(baseline, 2),
        "simulated_today_earning": today_earn,
        "income_drop_pct": round(drop, 4),
        "gate1_external": gate1,
        "gate2_income_drop": gate2,
        "dual_gate_open": gate1 and gate2,
        "claim_created": False,
        "message": "",
    }

    if not policy:
        result["message"] = "No active weekly policy — no payout"
        return result

    if not (gate1 and gate2):
        result["message"] = "Dual-gate not satisfied"
        return result

    event_id = f"evt_{uuid.uuid4().hex[:12]}"
    zone_id = user.zone_id
    income_loss = max(0.0, baseline - today_earn)
    fraud = evaluate_claim(db, user, zone_id, event_id, drop)

    ev = DisruptionEvent(
        event_id=event_id,
        zone_id=zone_id,
        disruption_type=json.dumps(ext["flags"]),
        severity=drop,
        external_confirmed=True,
        raw_payload=json.dumps(ext["details"])[:2000],
    )
    db.add(ev)

    payout_amt = payout_formula(income_loss, policy.max_per_event)
    status = "pending"
    payout_ref = ""

    if fraud.approved and fraud.score < 0.75:
        status = "paid"
        _, payout_ref = initiate_payout(user.upi_id, int(payout_amt * 100), "surakshapay_parametric")
    elif fraud.approved:
        status = "review"
    else:
        status = "rejected"
        payout_amt = 0.0

    active = [k for k, v in ext["flags"].items() if v]
    dtype = active[0] if len(active) == 1 else ("combined:" + ",".join(active[:3]))
    claim = Claim(
        user_id=user.id,
        policy_id=policy.id,
        event_id=event_id,
        disruption_type=dtype[:60],
        income_loss=round(income_loss, 2),
        payout_amount=payout_amt,
        status=status,
        fraud_score=fraud.score,
        fraud_notes=fraud.notes,
        payout_ref=payout_ref,
    )
    db.add(claim)
    db.commit()
    db.refresh(claim)

    result["claim_created"] = True
    result["claim_id"] = claim.id
    result["payout_amount"] = payout_amt
    result["fraud_score"] = fraud.score
    result["status"] = status
    result["message"] = "Claim evaluated"
    return result


async def run_pipeline_all_users(db: Session, force_mock: bool) -> list[dict]:
    users = db.query(User).all()
    out = []
    for u in users:
        out.append(await run_pipeline_for_user(db, u, force_mock_disruption=force_mock))
    return out

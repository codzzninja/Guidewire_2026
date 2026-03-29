"""Rule-based fraud checks + simple score (Phase 2). Isolation Forest reserved for Phase 3."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.claim import Claim
from app.models.user import User


@dataclass
class FraudResult:
    score: float
    notes: str
    approved: bool


def gps_in_zone(user: User, event_zone_id: str) -> bool:
    return user.zone_id == event_zone_id


def duplicate_event(db: Session, user_id: int, event_id: str) -> bool:
    exists = (
        db.query(Claim)
        .filter(Claim.user_id == user_id, Claim.event_id == event_id, Claim.status == "paid")
        .first()
    )
    return exists is not None


def evaluate_claim(
    db: Session,
    user: User,
    event_zone_id: str,
    event_id: str,
    income_drop_pct: float,
) -> FraudResult:
    notes = []
    score = 0.1

    if not gps_in_zone(user, event_zone_id):
        score = 0.95
        notes.append("GPS/zone mismatch with disruption zone")
        return FraudResult(score=score, notes="; ".join(notes), approved=False)

    if duplicate_event(db, user.id, event_id):
        score = 0.92
        notes.append("Duplicate payout for same event")
        return FraudResult(score=score, notes="; ".join(notes), approved=False)

    if income_drop_pct < 0.4:
        score = 0.55
        notes.append("Income drop below threshold (possible inactivity)")
    else:
        notes.append("Income drop consistent with disruption")

    if income_drop_pct > 0.85:
        score += 0.15
        notes.append("Extreme drop — elevated review")

    approved = score < 0.75
    return FraudResult(score=min(score, 0.99), notes="; ".join(notes), approved=approved)

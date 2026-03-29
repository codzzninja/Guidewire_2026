from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models.policy import Policy, PolicyStatus
from app.models.user import User
from app.schemas.policy import PlanQuoteIn, PolicyOut, PremiumQuoteOut
from app.services.premium_xgb import quote_plan

router = APIRouter(prefix="/policies", tags=["policies"])


def _week_window() -> tuple[date, date]:
    today = date.today()
    start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=6)
    return start, end


@router.post("/quote", response_model=PremiumQuoteOut)
def quote(body: PlanQuoteIn, user: User = Depends(get_current_user)):
    q = quote_plan(user, body.plan_type)
    return PremiumQuoteOut(**q)


@router.post("/subscribe", response_model=PolicyOut)
def subscribe(body: PlanQuoteIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = quote_plan(user, body.plan_type)
    start, end = _week_window()
    existing = (
        db.query(Policy)
        .filter(
            Policy.user_id == user.id,
            Policy.status == PolicyStatus.active.value,
            Policy.week_start == start,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Already subscribed for this week")
    p = Policy(
        user_id=user.id,
        plan_type=body.plan_type,
        weekly_premium=q["final_weekly_premium"],
        max_weekly_coverage=q["max_weekly_coverage"],
        max_per_event=q["max_per_event"],
        status=PolicyStatus.active.value,
        week_start=start,
        week_end=end,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.get("/active", response_model=PolicyOut | None)
def active_policy(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    start, _ = _week_window()
    p = (
        db.query(Policy)
        .filter(
            Policy.user_id == user.id,
            Policy.status == PolicyStatus.active.value,
            Policy.week_start == start,
        )
        .first()
    )
    return p

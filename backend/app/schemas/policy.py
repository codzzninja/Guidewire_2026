from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class PlanQuoteIn(BaseModel):
    plan_type: str = Field(..., pattern="^(basic|standard|pro)$")


class PolicyOut(BaseModel):
    id: int
    plan_type: str
    weekly_premium: float
    max_weekly_coverage: float
    max_per_event: float
    status: str
    week_start: date
    week_end: date

    model_config = {"from_attributes": True}


class PremiumQuoteOut(BaseModel):
    plan_type: str
    base_weekly_premium: float
    ml_risk_adjustment: float
    zone_safety_premium_credit: float
    risk_adjustment: float
    final_weekly_premium: float
    max_weekly_coverage: float
    max_per_event: float
    feature_snapshot: dict[str, Any]
    pricing_explainability: dict[str, Any]
    dynamic_coverage: dict[str, Any]

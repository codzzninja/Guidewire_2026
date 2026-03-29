from datetime import datetime
from pydantic import BaseModel


class ClaimOut(BaseModel):
    id: int
    event_id: str
    disruption_type: str
    income_loss: float
    payout_amount: float
    status: str
    fraud_score: float
    fraud_notes: str
    payout_ref: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TriggerSimulateIn(BaseModel):
    zone_id: str | None = None
    force_mock_disruption: bool = False

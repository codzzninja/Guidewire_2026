from fastapi import Depends
from sqlalchemy.orm import Session

from fastapi import APIRouter

from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.schemas.claim import TriggerSimulateIn
from app.services.triggers import evaluate_external_triggers, run_pipeline_for_user

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/live")
async def live_triggers(user: User = Depends(get_current_user)):
    """Poll weather + AQI + mock social triggers (no claim)."""
    return await evaluate_external_triggers(user.lat, user.lon, force_mock=False)


@router.post("/evaluate")
async def evaluate_self(
    body: TriggerSimulateIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Run parametric pipeline for the current user (demo: use force_mock_disruption=true)."""
    return await run_pipeline_for_user(db, user, force_mock_disruption=body.force_mock_disruption)

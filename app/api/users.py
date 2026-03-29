import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/users", tags=["users"])


class EarningsPatch(BaseModel):
    last_7_days_earnings: list[float] = Field(..., min_length=7, max_length=7)


@router.patch("/me/earnings")
def patch_earnings(
    body: EarningsPatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    for x in body.last_7_days_earnings:
        if x < 0:
            raise HTTPException(400, "Earnings must be non-negative")
    user.earnings_json = json.dumps(body.last_7_days_earnings)
    db.add(user)
    db.commit()
    return {"ok": True, "earnings_json": user.earnings_json}

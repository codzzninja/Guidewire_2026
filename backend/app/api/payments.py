"""Razorpay Test Mode: create order → Checkout → verify → credit today's earning."""

import json
import uuid
from typing import Any

import razorpay
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from razorpay.errors import SignatureVerificationError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.services.earnings_ledger import credit_today_from_payment

router = APIRouter(tags=["payments"])


def _client() -> razorpay.Client:
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise HTTPException(
            status_code=503,
            detail="Add RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET (Test mode) in backend/.env",
        )
    return razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))


class CreateOrderIn(BaseModel):
    amount_paise: int = Field(
        10_000,
        ge=100,
        description="Amount in paise (min ₹1). Default 10000 = ₹100.",
    )


class CreateOrderOut(BaseModel):
    order_id: str
    amount: int
    currency: str
    key_id: str


class VerifyIn(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


@router.post("/payments/razorpay/order", response_model=CreateOrderOut)
def create_test_order(
    body: CreateOrderIn,
    user: User = Depends(get_current_user),
):
    """Create a Razorpay Order for Checkout (Test mode — no real money)."""
    client = _client()
    receipt = f"sp{user.id}_{uuid.uuid4().hex[:12]}"[:40]
    try:
        order = client.order.create(
            {
                "amount": body.amount_paise,
                "currency": "INR",
                "receipt": receipt,
                "notes": {
                    "suraksha_user_id": str(user.id),
                    "product": "suraksha_test_earning",
                },
            }
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Razorpay order failed: {e}") from e

    oid = order.get("id")
    if not oid:
        raise HTTPException(status_code=502, detail="Razorpay returned no order id")
    return CreateOrderOut(
        order_id=oid,
        amount=body.amount_paise,
        currency="INR",
        key_id=settings.razorpay_key_id,
    )


@router.post("/payments/razorpay/verify")
def verify_checkout_payment(
    body: VerifyIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Verify payment signature from Checkout `handler`, then credit today's earning.
    Use Test UPI e.g. success@razorpay in Razorpay Test mode.
    """
    client = _client()
    try:
        client.utility.verify_payment_signature(
            {
                "razorpay_order_id": body.razorpay_order_id,
                "razorpay_payment_id": body.razorpay_payment_id,
                "razorpay_signature": body.razorpay_signature,
            }
        )
    except SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail="Invalid payment signature") from e

    try:
        order: dict[str, Any] = client.order.fetch(body.razorpay_order_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not fetch order: {e}") from e

    notes = order.get("notes") or {}
    if str(notes.get("suraksha_user_id")) != str(user.id):
        raise HTTPException(status_code=403, detail="Order does not belong to this user")

    try:
        pay: dict[str, Any] = client.payment.fetch(body.razorpay_payment_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not fetch payment: {e}") from e

    status = (pay.get("status") or "").lower()
    if status not in ("captured", "authorized"):
        raise HTTPException(status_code=400, detail=f"Payment not usable (status={status})")

    amount_paise = int(pay.get("amount") or 0)
    if amount_paise < 100:
        raise HTTPException(status_code=400, detail="Invalid payment amount")

    applied, msg = credit_today_from_payment(
        db,
        user,
        payment_id=body.razorpay_payment_id,
        order_id=body.razorpay_order_id,
        amount_paise=amount_paise,
    )
    amount_inr = round(amount_paise / 100.0, 2)
    return {
        "ok": True,
        "credited": applied,
        "message": msg,
        "amount_inr": amount_inr,
        "payment_id": body.razorpay_payment_id,
    }


@router.post("/webhooks/razorpay")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Optional: configure the same URL in Razorpay Dashboard → Webhooks (Test mode).
    Requires RAZORPAY_WEBHOOK_SECRET from the webhook settings page.
    """
    if not settings.razorpay_webhook_secret.strip():
        raise HTTPException(
            status_code=503,
            detail="Set RAZORPAY_WEBHOOK_SECRET to enable webhooks",
        )

    raw = await request.body()
    sig = request.headers.get("X-Razorpay-Signature") or ""
    client = _client()
    try:
        client.utility.verify_webhook_signature(
            raw.decode("utf-8") if isinstance(raw, bytes) else raw,
            sig,
            settings.razorpay_webhook_secret.strip(),
        )
    except SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail="Invalid webhook signature") from e

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from e

    event = data.get("event") or ""
    if event != "payment.captured":
        return {"ok": True, "ignored": event}

    pay_ent = (data.get("payload") or {}).get("payment", {}).get("entity") or {}
    payment_id = pay_ent.get("id")
    order_id = pay_ent.get("order_id")
    amount_paise = pay_ent.get("amount")
    if not payment_id or not order_id or amount_paise is None:
        raise HTTPException(status_code=400, detail="Webhook payload missing payment fields")

    try:
        order: dict[str, Any] = client.order.fetch(order_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not fetch order: {e}") from e

    notes = order.get("notes") or {}
    uid = notes.get("suraksha_user_id")
    if not uid:
        return {"ok": True, "skipped": "not_suraksha_order"}

    user = db.query(User).filter(User.id == int(uid)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User in order notes not found")

    apaise = int(amount_paise)
    applied, msg = credit_today_from_payment(
        db,
        user,
        payment_id=payment_id,
        order_id=order_id,
        amount_paise=apaise,
    )
    return {
        "ok": True,
        "credited": applied,
        "message": msg,
    }

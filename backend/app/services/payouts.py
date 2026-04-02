"""Razorpay: real Test Mode Order API (visible in Razorpay dashboard)."""

import uuid

import razorpay

from app.config import settings
from app.services.errors import IntegrationError


def initiate_payout(upi: str, amount_paise: int, purpose: str) -> tuple[str, str]:
    """
    Creates a real `order` in Razorpay Test Mode (amount in paise, INR).
    For production UPI payouts to partners, use RazorpayX Payouts + linked account.
    """
    ref = f"sp_{uuid.uuid4().hex[:14]}"
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        if settings.allow_mocks or settings.razorpay_optional:
            return "simulated_paid", ref
        raise IntegrationError(
            "Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET, or set RAZORPAY_OPTIONAL=true.",
            "razorpay",
        )

    client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
    amt = max(int(amount_paise), 100)  # minimum 100 paise (₹1) in test
    try:
        order = client.order.create(
            {
                "amount": amt,
                "currency": "INR",
                "receipt": ref[:40],
                "notes": {
                    "purpose": purpose,
                    "payee_upi": upi,
                    "product": "surakshapay_parametric",
                },
            }
        )
    except Exception as e:
        raise IntegrationError(f"Razorpay order failed: {e}", "razorpay") from e

    oid = order.get("id", ref)
    return "razorpay_order_created", oid

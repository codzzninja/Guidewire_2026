"""Razorpay payout simulation — uses Orders API pattern or mock reference."""

import uuid

from app.config import settings


def initiate_payout(upi: str, amount_paise: int, purpose: str) -> tuple[str, str]:
    """
    Returns (status, reference_id).
    With credentials: creates a real test-mode order/payment attempt where possible.
    Without: returns mock success for demo.
    """
    ref = f"sp_{uuid.uuid4().hex[:16]}"
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        return "simulated_paid", ref
    try:
        import razorpay

        client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
        # Razorpay Payouts need linked account; for hackathon we record intent only
        _ = client
        return "razorpay_configured_mock_paid", ref
    except Exception:
        return "simulated_paid", ref

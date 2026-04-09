from __future__ import annotations  # Python 3.9 compatibility: allows X | Y union syntax

# server/services/phone_verification.py
"""Phone number verification via Twilio Verify API."""

import logging
import os

from twilio.rest import Client

logger = logging.getLogger("dispatch.phone_verification")

_client: Client | None = None


class VerificationServiceError(RuntimeError):
    """Raised when verification checks cannot be completed."""


def _get_client() -> tuple[Client, str]:
    global _client
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    service_sid = os.environ.get("TWILIO_VERIFY_SERVICE_SID", "")
    if not account_sid:
        raise RuntimeError("TWILIO_ACCOUNT_SID is not set")
    if not auth_token:
        raise RuntimeError("TWILIO_AUTH_TOKEN is not set")
    if not service_sid:
        raise RuntimeError("TWILIO_VERIFY_SERVICE_SID is not set")
    if _client is None:
        _client = Client(account_sid, auth_token)
    return _client, service_sid


def send_verification(phone_number: str) -> bool:
    """Send an SMS OTP to the given phone number via Twilio Verify.

    Returns True on success, False on failure.
    """
    try:
        client, service_sid = _get_client()
        client.verify.v2.services(service_sid).verifications.create(
            to=phone_number, channel="sms"
        )
        logger.info("send_verification sent to phone=%r", phone_number)
        return True
    except Exception as e:
        logger.error("send_verification failed for phone=%r: %r", phone_number, e)
        return False


def check_verification(phone_number: str, code: str) -> bool:
    """Check a Twilio Verify OTP code for the given phone number.

    Returns True if the code is approved, False otherwise.
    """
    try:
        client, service_sid = _get_client()
        result = client.verify.v2.services(service_sid).verification_checks.create(
            to=phone_number, code=code
        )
        approved = result.status == "approved"
        logger.info(
            "check_verification phone=%r status=%r approved=%s",
            phone_number,
            result.status,
            approved,
        )
        return approved
    except Exception as e:
        logger.error("check_verification failed for phone=%r: %r", phone_number, e)
        raise VerificationServiceError("Verification service unavailable") from e

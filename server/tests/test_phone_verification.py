"""Unit tests for services/phone_verification.py."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# Helper: build a mock Twilio client that returns controllable results.

def _make_twilio_client(verification_status: str = "pending"):
    """Return a mock Twilio Client whose verify chain returns the given status."""
    client = MagicMock()

    # send_verification path: client.verify.v2.services(sid).verifications.create(...)
    client.verify.v2.services.return_value.verifications.create.return_value = MagicMock()

    # check_verification path: client.verify.v2.services(sid).verification_checks.create(...)
    check_result = MagicMock()
    check_result.status = verification_status
    client.verify.v2.services.return_value.verification_checks.create.return_value = check_result

    return client


TWILIO_ENV = {
    "TWILIO_ACCOUNT_SID": "ACtest000",
    "TWILIO_AUTH_TOKEN": "authtest",
    "TWILIO_VERIFY_SERVICE_SID": "VAtest000",
}


# ==================== send_verification ====================


class TestSendVerification:
    def test_success_returns_true(self):
        mock_client = _make_twilio_client()

        with patch.dict("os.environ", TWILIO_ENV):
            import services.phone_verification as pv
            # Reset cached client so our mock is used fresh.
            pv._client = None
            with patch("services.phone_verification.Client", return_value=mock_client):
                result = pv.send_verification("+12125551234")

        assert result is True

    def test_success_calls_twilio_verifications_create(self):
        mock_client = _make_twilio_client()

        with patch.dict("os.environ", TWILIO_ENV):
            import services.phone_verification as pv
            pv._client = None
            with patch("services.phone_verification.Client", return_value=mock_client):
                pv.send_verification("+12125551234")

        mock_client.verify.v2.services.return_value.verifications.create.assert_called_once_with(
            to="+12125551234", channel="sms"
        )

    def test_failure_returns_false(self):
        mock_client = _make_twilio_client()
        mock_client.verify.v2.services.return_value.verifications.create.side_effect = (
            RuntimeError("Twilio unavailable")
        )

        with patch.dict("os.environ", TWILIO_ENV):
            import services.phone_verification as pv
            pv._client = None
            with patch("services.phone_verification.Client", return_value=mock_client):
                result = pv.send_verification("+12125551234")

        assert result is False

    def test_missing_account_sid_returns_false(self):
        """If env vars are missing, _get_client raises; send_verification returns False."""
        import services.phone_verification as pv
        pv._client = None

        env_without_sid = {
            "TWILIO_ACCOUNT_SID": "",
            "TWILIO_AUTH_TOKEN": "authtest",
            "TWILIO_VERIFY_SERVICE_SID": "VAtest000",
        }
        with patch.dict("os.environ", env_without_sid, clear=False):
            result = pv.send_verification("+12125551234")

        assert result is False


# ==================== check_verification ====================


class TestCheckVerification:
    def test_approved_status_returns_true(self):
        mock_client = _make_twilio_client(verification_status="approved")

        with patch.dict("os.environ", TWILIO_ENV):
            import services.phone_verification as pv
            pv._client = None
            with patch("services.phone_verification.Client", return_value=mock_client):
                result = pv.check_verification("+12125551234", "123456")

        assert result is True

    def test_pending_status_returns_false(self):
        mock_client = _make_twilio_client(verification_status="pending")

        with patch.dict("os.environ", TWILIO_ENV):
            import services.phone_verification as pv
            pv._client = None
            with patch("services.phone_verification.Client", return_value=mock_client):
                result = pv.check_verification("+12125551234", "999999")

        assert result is False

    def test_expired_status_returns_false(self):
        mock_client = _make_twilio_client(verification_status="expired")

        with patch.dict("os.environ", TWILIO_ENV):
            import services.phone_verification as pv
            pv._client = None
            with patch("services.phone_verification.Client", return_value=mock_client):
                result = pv.check_verification("+12125551234", "000000")

        assert result is False

    def test_twilio_exception_raises_service_error(self):
        mock_client = _make_twilio_client()
        mock_client.verify.v2.services.return_value.verification_checks.create.side_effect = (
            RuntimeError("Network error")
        )

        with patch.dict("os.environ", TWILIO_ENV):
            import services.phone_verification as pv
            pv._client = None
            with patch("services.phone_verification.Client", return_value=mock_client):
                with pytest.raises(pv.VerificationServiceError):
                    pv.check_verification("+12125551234", "123456")

    def test_calls_verification_checks_create_with_correct_args(self):
        mock_client = _make_twilio_client(verification_status="approved")

        with patch.dict("os.environ", TWILIO_ENV):
            import services.phone_verification as pv
            pv._client = None
            with patch("services.phone_verification.Client", return_value=mock_client):
                pv.check_verification("+19998887777", "654321")

        mock_client.verify.v2.services.return_value.verification_checks.create.assert_called_once_with(
            to="+19998887777", code="654321"
        )

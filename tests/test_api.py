"""
Black-box API tests using FastAPI's TestClient.
These tests do NOT call the real LLM — they patch analyze_ticket to isolate
the HTTP layer, schema validation, safety checks, and fallback logic.
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from models import (
    AnalyzeResponse,
    EvidenceVerdict,
    CaseType,
    Severity,
    Department,
)

# Patch the LLM client before importing the app so startup validation passes.
_mock_anthropic = MagicMock()
_mock_anthropic_module = MagicMock()
_mock_anthropic_module.Anthropic.return_value = _mock_anthropic

import sys
sys.modules.setdefault("anthropic", _mock_anthropic_module)

import os
os.environ.setdefault("LLM_PROVIDER", "anthropic")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-key")

from main import app  # noqa: E402 — must come after env setup

client = TestClient(app)

# Minimal valid request body reused across multiple tests.
_BASE_REQUEST = {
    "ticket_id": "TKT-TEST-001",
    "complaint": "I sent money to the wrong number and need help.",
    "language": "en",
    "channel": "in_app_chat",
    "user_type": "customer",
    "transaction_history": [
        {
            "transaction_id": "TXN-001",
            "timestamp": "2026-01-01T10:00:00Z",
            "type": "transfer",
            "amount": 1000.0,
            "counterparty": "+8801700000001",
            "status": "completed",
        }
    ],
}

# Standard mock response returned by analyze_ticket in happy-path tests.
_MOCK_RESPONSE = AnalyzeResponse(
    ticket_id="TKT-TEST-001",
    relevant_transaction_id="TXN-001",
    evidence_verdict=EvidenceVerdict.CONSISTENT,
    case_type=CaseType.WRONG_TRANSFER,
    severity=Severity.MEDIUM,
    department=Department.DISPUTE_RESOLUTION,
    agent_summary="Customer transferred 1000 BDT to the wrong number.",
    recommended_next_action="Initiate dispute resolution for TXN-001.",
    customer_reply="We have received your complaint and our team is investigating.",
    human_review_required=True,
    confidence=0.9,
    reason_codes=["wrong_transfer", "transaction_match"],
)


class TestHealth:
    def test_health_returns_ok(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_health_method_not_allowed(self):
        # POST to /health should 405, not 500.
        response = client.post("/health")
        assert response.status_code == 405


class TestSchemaValidation:
    def test_missing_ticket_id_returns_422(self):
        body = {k: v for k, v in _BASE_REQUEST.items() if k != "ticket_id"}
        response = client.post("/analyze-ticket", json=body)
        assert response.status_code == 422

    def test_missing_complaint_returns_422(self):
        body = {k: v for k, v in _BASE_REQUEST.items() if k != "complaint"}
        response = client.post("/analyze-ticket", json=body)
        assert response.status_code == 422

    def test_blank_complaint_returns_422(self):
        body = {**_BASE_REQUEST, "complaint": "   "}
        response = client.post("/analyze-ticket", json=body)
        assert response.status_code == 422

    def test_invalid_channel_returns_422(self):
        body = {**_BASE_REQUEST, "channel": "carrier_pigeon"}
        response = client.post("/analyze-ticket", json=body)
        assert response.status_code == 422

    def test_invalid_user_type_returns_422(self):
        body = {**_BASE_REQUEST, "user_type": "robot"}
        response = client.post("/analyze-ticket", json=body)
        assert response.status_code == 422

    def test_control_chars_in_ticket_id_returns_422(self):
        # ticket_id is echoed into the LLM prompt — control chars must be rejected.
        body = {**_BASE_REQUEST, "ticket_id": "TKT\x00BAD"}
        response = client.post("/analyze-ticket", json=body)
        assert response.status_code == 422

    def test_whitespace_only_ticket_id_returns_422(self):
        body = {**_BASE_REQUEST, "ticket_id": "   "}
        response = client.post("/analyze-ticket", json=body)
        assert response.status_code == 422


class TestHappyPath:
    def test_analyze_ticket_returns_200_and_correct_shape(self):
        with patch("main.analyze_ticket", return_value=_MOCK_RESPONSE):
            response = client.post("/analyze-ticket", json=_BASE_REQUEST)
        assert response.status_code == 200
        data = response.json()
        assert data["ticket_id"] == "TKT-TEST-001"
        assert data["relevant_transaction_id"] == "TXN-001"
        assert data["evidence_verdict"] == "consistent"
        assert data["case_type"] == "wrong_transfer"
        assert data["human_review_required"] is True
        assert isinstance(data["confidence"], float)
        assert isinstance(data["reason_codes"], list)

    def test_no_transaction_history_accepted(self):
        # transaction_history is optional — omitting it must not crash.
        body = {
            "ticket_id": "TKT-NOTXN",
            "complaint": "My account balance looks wrong.",
        }
        no_txn_response = AnalyzeResponse(
            ticket_id="TKT-NOTXN",
            relevant_transaction_id=None,
            evidence_verdict=EvidenceVerdict.INSUFFICIENT_DATA,
            case_type=CaseType.OTHER,
            severity=Severity.LOW,
            department=Department.CUSTOMER_SUPPORT,
            agent_summary="No transactions provided.",
            recommended_next_action="Request transaction history from the customer.",
            customer_reply="We have received your complaint and will investigate.",
            human_review_required=True,
            confidence=0.5,
            reason_codes=["no_transactions"],
        )
        with patch("main.analyze_ticket", return_value=no_txn_response):
            response = client.post("/analyze-ticket", json=body)
        assert response.status_code == 200


class TestSafetyGuardrails:
    def test_safe_customer_reply_preserved(self):
        with patch("main.analyze_ticket", return_value=_MOCK_RESPONSE):
            response = client.post("/analyze-ticket", json=_BASE_REQUEST)
        assert "pin" not in response.json()["customer_reply"].lower()
        assert "otp" not in response.json()["customer_reply"].lower()
        assert "refund approved" not in response.json()["customer_reply"].lower()


class TestSafeCustomerReplyUnit:
    """Direct unit tests for the Python-layer safety scrubber in analyzer.py."""

    def test_pin_request_replaced_with_fallback(self):
        from analyzer import _safe_customer_reply, _SAFE_FALLBACK_REPLY
        unsafe = "Please provide your pin so we can verify your account."
        assert _safe_customer_reply(unsafe) == _SAFE_FALLBACK_REPLY

    def test_otp_request_replaced_with_fallback(self):
        from analyzer import _safe_customer_reply, _SAFE_FALLBACK_REPLY
        unsafe = "Please enter your otp to proceed."
        assert _safe_customer_reply(unsafe) == _SAFE_FALLBACK_REPLY

    def test_refund_approved_replaced_with_fallback(self):
        from analyzer import _safe_customer_reply, _SAFE_FALLBACK_REPLY
        unsafe = "Your refund has been approved and will arrive shortly."
        assert _safe_customer_reply(unsafe) == _SAFE_FALLBACK_REPLY

    def test_negated_pin_warning_is_preserved(self):
        # "never ask for your pin" is a safety reminder — must NOT be scrubbed.
        from analyzer import _safe_customer_reply
        safe = "Please note that we will never ask for your pin or otp."
        assert _safe_customer_reply(safe) == safe

    def test_clean_reply_is_unchanged(self):
        from analyzer import _safe_customer_reply
        safe = "We have received your complaint and our team is investigating."
        assert _safe_customer_reply(safe) == safe


class TestPhishingDetectionUnit:
    """Direct unit tests for the Python-level phishing keyword detector."""

    def test_otp_in_complaint_triggers_phishing(self):
        from analyzer import _detect_phishing
        assert _detect_phishing("Someone called me and asked for my OTP") is True

    def test_bangla_pin_triggers_phishing(self):
        from analyzer import _detect_phishing
        assert _detect_phishing("কেউ আমার পিন চেয়েছে") is True

    def test_normal_complaint_not_phishing(self):
        from analyzer import _detect_phishing
        assert _detect_phishing("My payment failed yesterday morning.") is False


class TestHighValueEscalationUnit:
    """Unit tests for the Python-level high-value severity escalation logic."""

    def test_max_transaction_amount_returns_correct_max(self):
        from analyzer import _max_transaction_amount
        from models import TransactionItem, TransactionType, TransactionStatus
        txns = [
            TransactionItem(
                transaction_id="T1", timestamp="2026-01-01T10:00:00Z",
                type=TransactionType.TRANSFER, amount=1000.0,
                counterparty="+8801700000001", status=TransactionStatus.COMPLETED,
            ),
            TransactionItem(
                transaction_id="T2", timestamp="2026-01-01T11:00:00Z",
                type=TransactionType.PAYMENT, amount=6000.0,
                counterparty="+8801700000002", status=TransactionStatus.COMPLETED,
            ),
        ]
        assert _max_transaction_amount(txns) == 6000.0

    def test_max_transaction_amount_empty_returns_zero(self):
        from analyzer import _max_transaction_amount
        assert _max_transaction_amount([]) == 0.0


class TestFallback:
    def test_analyze_ticket_returns_fallback_on_exception(self):
        # TestClient re-raises by default — disable to let the global handler produce a 500 response.
        error_client = TestClient(app, raise_server_exceptions=False)
        with patch("main.analyze_ticket", side_effect=RuntimeError("LLM unavailable")):
            response = error_client.post("/analyze-ticket", json=_BASE_REQUEST)
        assert response.status_code == 500
        data = response.json()
        # Global handler must not leak the raw exception message to the caller.
        assert "LLM unavailable" not in str(data)
        assert "error" in data

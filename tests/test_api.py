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


class TestFallback:
    def test_analyze_ticket_returns_fallback_on_exception(self):
        # When analyze_ticket raises, the global handler must return 500 — not crash.
        with patch("main.analyze_ticket", side_effect=RuntimeError("LLM unavailable")):
            response = client.post("/analyze-ticket", json=_BASE_REQUEST)
        assert response.status_code == 500
        data = response.json()
        # Must not expose the raw exception message.
        assert "LLM unavailable" not in str(data)
        assert "error" in data or "detail" in data

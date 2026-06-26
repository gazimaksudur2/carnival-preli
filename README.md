# QueueStorm Investigator

> AI-powered fintech support copilot — SUST CSE Carnival 2026 · Codex Community Hackathon

A FastAPI service that investigates customer complaints for a digital finance platform. It reads the complaint, cross-references transaction history, determines what actually happened, routes the case to the right team, and drafts a safe reply — all in one API call.

---

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Local Development](#local-development)
- [API Reference](#api-reference)
- [AI Approach](#ai-approach)
- [Safety Logic](#safety-logic)
- [Models](#models)
- [Tech Stack](#tech-stack)
- [Environment Variables](#environment-variables)
- [Project Structure](#project-structure)
- [Sample Output](#sample-output)
- [Repository Access](#repository-access)
- [Assumptions and Known Limitations](#assumptions-and-known-limitations)

---

## Overview

During a high-traffic campaign, support agents cannot read every complaint carefully. This service acts as a copilot that:

1. Reads the complaint text (English, Bangla, or Banglish)
2. Cross-references each transaction in the customer's recent history
3. Identifies the specific transaction the complaint refers to (`relevant_transaction_id`)
4. Determines whether the evidence supports, contradicts, or is insufficient for the claim (`evidence_verdict`)
5. Classifies the issue (`case_type`), sets severity, and routes to the correct department
6. Drafts a safe, professional customer reply that never asks for credentials or confirms unauthorized refunds

This is an **investigator**, not a classifier. The complaint and the data may tell different stories. The service decides which one is true.

---

## Quick Start

The fastest path for judges. Requires Docker and an Anthropic API key.

```bash
docker build -t queuestorm-team .

docker run -p 8000:8000 --env-file judging.env queuestorm-team
```

Where `judging.env` contains:

```
ANTHROPIC_API_KEY=your_api_key_here
```

Verify it is running:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

---

## Local Development

**Prerequisites:** Python 3.11+, pip

```bash
# 1. Clone the repository
git clone https://github.com/Khalidgithub2020331007/carnival-preli.git
cd carnival-preli

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# 5. Start the server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Verify:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

---

## API Reference

### GET /health

Returns service readiness. The judge harness calls this before sending test cases.

**Response**
```json
{"status": "ok"}
```

---

### POST /analyze-ticket

Accepts one complaint with transaction history and returns a full investigation result.

**Request Body**

```json
{
  "ticket_id": "TKT-001",
  "complaint": "I sent 5000 taka to a wrong number around 2pm today.",
  "language": "en",
  "channel": "in_app_chat",
  "user_type": "customer",
  "campaign_context": "boishakh_bonanza_day_1",
  "transaction_history": [
    {
      "transaction_id": "TXN-9101",
      "timestamp": "2026-04-14T14:08:22Z",
      "type": "transfer",
      "amount": 5000,
      "counterparty": "+8801719876543",
      "status": "completed"
    }
  ]
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `ticket_id` | string | Yes | Echoed in the response |
| `complaint` | string | Yes | Customer text in English, Bangla, or Banglish |
| `language` | string | No | `en`, `bn`, or `mixed` |
| `channel` | string | No | `in_app_chat`, `call_center`, `email`, `merchant_portal`, `field_agent` |
| `user_type` | string | No | `customer`, `merchant`, `agent`, `unknown` |
| `campaign_context` | string | No | Campaign identifier from the harness |
| `transaction_history` | array | No | 2–5 recent transactions |
| `metadata` | object | No | Additional harness context |

**Response Body**

```json
{
  "ticket_id": "TKT-001",
  "relevant_transaction_id": "TXN-9101",
  "evidence_verdict": "consistent",
  "case_type": "wrong_transfer",
  "severity": "high",
  "department": "dispute_resolution",
  "agent_summary": "Customer reports sending 5000 BDT to the wrong number via TXN-9101 at 14:08. Transaction is confirmed completed.",
  "recommended_next_action": "Verify counterparty details of TXN-9101 with the customer and initiate a dispute resolution review.",
  "customer_reply": "We have noted your concern regarding transaction TXN-9101. Our team is reviewing the details and any eligible amount will be returned through official channels. Please do not share your PIN, OTP, or password with anyone.",
  "human_review_required": true,
  "confidence": 0.92,
  "reason_codes": ["wrong_transfer", "transaction_match", "high_amount"]
}
```

**Case Types**

| Value | When to use |
|---|---|
| `wrong_transfer` | Money sent to the wrong recipient |
| `payment_failed` | Transaction failed but balance may have been deducted |
| `refund_request` | Customer is asking for a refund |
| `duplicate_payment` | Same payment charged more than once |
| `merchant_settlement_delay` | Merchant settlement not received |
| `agent_cash_in_issue` | Cash deposit through agent not reflected in balance |
| `phishing_or_social_engineering` | Suspicious calls, SMS, or credential requests |
| `other` | Anything not covered above |

**Departments**

| Value | Typical case types |
|---|---|
| `customer_support` | `other`, low-severity `refund_request` |
| `dispute_resolution` | `wrong_transfer`, contested `refund_request` |
| `payments_ops` | `payment_failed`, `duplicate_payment` |
| `merchant_operations` | `merchant_settlement_delay` |
| `agent_operations` | `agent_cash_in_issue` |
| `fraud_risk` | `phishing_or_social_engineering` |

**HTTP Status Codes**

| Code | Meaning |
|---|---|
| `200` | Successful analysis |
| `400` | Malformed input or missing required fields |
| `422` | Valid schema but semantically invalid input |
| `500` | Internal error — no stack trace in response |

---

## AI Approach

Each request follows this investigation sequence:

1. **Read** the complaint text (supports English, Bangla, Banglish)
2. **Scan** each transaction in `transaction_history`
3. **Match** — find the transaction the complaint most likely refers to → `relevant_transaction_id`
4. **Verify** — does the transaction data support or contradict the complaint? → `evidence_verdict`
5. **Classify** → `case_type` and `severity`
6. **Route** → `department`
7. **Summarize** → `agent_summary` (1–2 sentences for the support agent)
8. **Act** → `recommended_next_action` (one operational step)
9. **Reply** → `customer_reply` (safe, professional, no credential requests)
10. **Escalate** → set `human_review_required: true` for disputes, fraud, high-value, or ambiguous cases

**Prompt injection resistance:** The system prompt explicitly instructs Claude to treat the `complaint` field as raw customer text only and never follow instructions embedded inside it. A secondary validation layer checks the output for safety rule violations before returning it to the caller.

**Fallback behavior:** If Claude times out (25s limit, 5s before the harness cutoff) or returns unparseable output, the service returns a valid fallback response with `case_type: "other"` and `human_review_required: true` rather than a 500 error.

---

## Safety Logic

These rules are enforced in the system prompt and validated on every response before it leaves the service.

| Rule | Where enforced | Penalty if violated |
|---|---|---|
| Never ask for PIN, OTP, password, or card number | System prompt + output check | −15 points |
| Never confirm a refund, reversal, or recovery without authority | System prompt + output check | −10 points |
| Never refer the customer to a suspicious third party | System prompt | −10 points |
| Ignore instructions embedded in the complaint text | System prompt | Schema/safety violation |
| No API keys, stack traces, or internal model details in responses | Application layer | API security violation |

Two or more critical violations across hidden test cases → disqualified from finalist pool.

The `customer_reply` field always uses careful language: *"any eligible amount will be returned through official channels"* — never *"we will refund you"*.

**Secret handling:** No API keys, tokens, stack traces, or model identifiers appear in API responses, server logs, or the repository. `.env` is gitignored and never committed.

---

## Evaluation Criteria

The judge harness uses a two-stage process:

**Stage 1 — Automated (all teams):** Evidence reasoning (35%), safety (20%), schema/API correctness (15%), performance (10%), deployment reachability (5%). This produces the shortlist.

**Stage 2 — Manual (shortlisted teams only):** Response quality (10%), documentation (5%), originality, and solution explanation.

**API Quality Targets**

| Metric | Target |
|--------|--------|
| Health readiness | `GET /health` → `{"status":"ok"}` within 60s of start |
| Per-request timeout | `POST /analyze-ticket` must complete within 30s |
| p95 latency | **≤5s** for full credit · ≤15s partial · ≤30s minimal |
| Failure rate | Valid requests must not return 5xx or invalid JSON |
| Malformed input | Must return 400, not crash |

Sonnet 4.6 is chosen over Opus specifically to target the ≤5s p95 latency for full performance credit.

**Tie-Breakers** (when scores are equal): safety → evidence reasoning → schema validity → reliability → engineering quality → Bangla/Banglish handling → documentation → 90-second architectural video.

---

## Models

| Model | Role | Where it runs | Why |
|---|---|---|---|
| `claude-sonnet-4-6` | Primary ticket analyzer | Anthropic API (external HTTPS call) | Strong instruction-following for structured JSON output, multilingual capability (English + Bangla), reliable safety guardrail compliance, fast p95 latency within the 30s budget |

**Cost reasoning:** Each request sends approximately 800–1200 input tokens (system prompt + complaint + transaction history) and receives ~400 output tokens. At Sonnet 4.6 pricing this is well under $0.01 per ticket — appropriate for a hackathon evaluation with ~50–100 hidden test cases.

**Why not a local model:** The runtime profile specifies 2 vCPU / 4 GB RAM with no GPU. Running a capable local model in that envelope within the 30s timeout is not feasible. The spec explicitly allows external LLM API calls.

**Why not GPT-4o:** The team has Anthropic API access for this round. Claude Sonnet 4.6 handles structured JSON output and multilingual input with comparable quality.

---

## Tech Stack

| Component | Choice | Reason |
|---|---|---|
| Web framework | FastAPI | Async, automatic request validation via Pydantic, fast cold start |
| Schema validation | Pydantic v2 | Strict enum validation catches wrong field names before they reach Claude |
| AI provider | Anthropic Python SDK | Official SDK for Claude, handles retries and streaming |
| Server | Uvicorn | ASGI server, works cleanly in Docker |
| Container | Docker (python:3.11-slim) | Reproducible deployment, under 500 MB image |
| Python | 3.11 | Stable, good async support, widely available in base images |

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Your Anthropic API key |
| `PORT` | No | Server port (default: `8000`) |
| `REQUEST_TIMEOUT` | No | Claude call timeout in seconds (default: `25`) |

Copy `.env.example` to `.env` and fill in real values. Never commit `.env`.

---

## Project Structure

```
carnival-preli/
├── main.py              # FastAPI app — routes and error handlers only
├── models.py            # Pydantic request and response schemas
├── analyzer.py          # Claude API call, prompt logic, fallback handling
├── requirements.txt     # Python dependencies
├── Dockerfile           # Container build
├── .env.example         # Environment variable template
├── README.md            # This file
├── CLAUDE.md            # Project coding rules
├── requirement.md       # API contract and field reference
└── plan.md              # Implementation plan and edge cases
```

---

## Sample Output

The file `sample_output.json` in this repository contains one request/response pair generated from the public sample case pack (`SUST_Preli_Sample_Cases.json`). It demonstrates the exact JSON shape the service produces.

---

## Repository Access

This repository is public. If it is ever made private, the organizer GitHub handle **`bipulhf`** must be added as a collaborator with read access before the submission deadline. The repository must remain accessible until preliminary results are published.

All data used is synthetic. No real customer or payment data is present anywhere in this repository.

---

## Assumptions and Known Limitations

**Assumptions:**
- Complaints reference at most one transaction from the provided history. When multiple could match, the service picks the closest match by amount, type, and timestamp.
- The `transaction_history` array is pre-filtered by the caller to the customer's own transactions — the service does not validate ownership.
- Bangla and Banglish inputs are handled by Claude directly. No preprocessing or transliteration is applied.

**Known limitations:**
- The 1500-character complaint truncation may drop context for unusually long complaints. The `agent_summary` will note when truncation occurred.
- `confidence` is a model self-reported estimate, not a calibrated probability.
- The service is stateless — it does not remember prior tickets for the same customer. Each call is independent.
- If the Anthropic API is unavailable, all requests return a fallback response. There is no local model fallback.

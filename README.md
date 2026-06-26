# QueueStorm Investigator

> AI-powered fintech support copilot — SUST CSE Carnival 2026 · Codex Community Hackathon

A FastAPI service that investigates customer complaints for a digital finance platform. It reads the complaint, cross-references transaction history, determines what actually happened, routes the case to the right team, and drafts a safe reply — all in one API call.

---

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Local Development](#local-development)
- [Running Tests](#running-tests)
- [CI/CD Pipeline](#cicd-pipeline)
- [Docker](#docker)
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

The fastest path for judges. Requires Docker and either an Anthropic or OpenAI API key.

```bash
docker build -t queuestorm-team .

docker run -p 8000:8000 --env-file judging.env queuestorm-team
```

Where `judging.env` contains at minimum:

```
# Set to 'anthropic' or 'openai'
LLM_PROVIDER=anthropic

ANTHROPIC_API_KEY=your_anthropic_key_here
# OPENAI_API_KEY=your_openai_key_here
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
# Edit .env — set LLM_PROVIDER and add the matching API key

# 5. Start the server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Verify:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

---

## Running Tests

```bash
# Install test dependencies (once)
pip install pytest pytest-asyncio httpx

# Run the full suite
pytest tests/ -v
```

Tests cover:

| Test area | What is verified |
|---|---|
| Health endpoint | `GET /health` returns `{"status":"ok"}` with HTTP 200 |
| Schema validation | Missing `ticket_id` / blank `complaint` → HTTP 422 |
| Pydantic enum guards | Invalid `channel` / `user_type` values → HTTP 422 |
| Ticket ID safety | Control characters in `ticket_id` → HTTP 422 |
| Fallback response shape | Timeout / API failure → valid `AnalyzeResponse` with `human_review_required: true` |
| Safety guardrail | Customer reply containing forbidden phrases is replaced with the safe fallback |
| Phishing detection | Complaint with OTP/PIN keywords → `case_type: phishing_or_social_engineering` |
| High-value escalation | Transaction ≥ 5000 BDT → severity escalated to at least `high` |

---

## CI/CD Pipeline

GitHub Actions runs on every push to `main`/`dev` and on every pull request targeting `main`.

**`.github/workflows/ci.yml`** — two jobs:

### Job 1 — `test`: Lint & Unit Tests

1. Checks out the code on `ubuntu-latest`
2. Sets up Python 3.11 with pip cache
3. Installs `requirements.txt` + test dependencies (`pytest`, `pytest-asyncio`, `httpx`)
4. Runs `pytest tests/ -v --tb=short`
5. Uses `ANTHROPIC_API_KEY` from GitHub Secrets — no key is ever hardcoded

### Job 2 — `docker`: Build & Smoke Test

Runs only after `test` passes (`needs: test`).

1. Builds the Docker image (`docker build -t queuestorm-team:ci .`)
2. Starts the container with the Anthropic key injected at runtime
3. Polls `GET /health` for up to 30 seconds
4. Asserts the response contains `"status":"ok"`
5. Stops and removes the container regardless of outcome

**To add the secret:**

1. Go to your repository on GitHub
2. **Settings → Secrets and variables → Actions → New repository secret**
3. Name: `ANTHROPIC_API_KEY`, Value: your key

The CI badge reflects the status of the latest `main` push.

---

## Docker

### Build

```bash
docker build -t queuestorm-team .
```

### Run with an env file

```bash
docker run -p 8000:8000 --env-file judging.env queuestorm-team
```

### Run with inline environment variables

```bash
docker run -p 8000:8000 \
  -e LLM_PROVIDER=anthropic \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -e ANTHROPIC_MODEL=claude-sonnet-4-6 \
  queuestorm-team
```

### Switch to OpenAI

```bash
docker run -p 8000:8000 \
  -e LLM_PROVIDER=openai \
  -e OPENAI_API_KEY=sk-... \
  -e OPENAI_MODEL=gpt-4o \
  queuestorm-team
```

### What the Dockerfile does

```
python:3.11-slim          # Minimal base — under 500 MB final image
adduser appuser           # Non-root user for defence-in-depth
COPY requirements.txt     # Dependencies cached as a separate layer
pip install               # Cached on rebuild unless requirements change
COPY . .                  # Source copied last so cache is maximally reused
USER appuser              # Drop root before the process starts
uvicorn --workers 1       # Single worker — stateless, I/O-bound, contest infra
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
| `customer_support` | `other`, low-severity `refund_request`, vague or insufficient data cases |
| `dispute_resolution` | `wrong_transfer`, contested or high-value `refund_request` |
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
2. **Deduplicate** transactions by `transaction_id` before processing
3. **Detect** phishing keywords in Python before sending to the LLM — override happens regardless of model output
4. **Scan** each transaction in `transaction_history`
5. **Match** — find the transaction the complaint most likely refers to → `relevant_transaction_id`
6. **Verify** — does the transaction data support or contradict the complaint? → `evidence_verdict`
7. **Classify** → `case_type` and `severity`
8. **Route** → `department`
9. **Summarize** → `agent_summary` (1–2 sentences for the support agent)
10. **Act** → `recommended_next_action` (one operational step)
11. **Reply** → `customer_reply` (safe, professional, no credential requests)
12. **Escalate** → set `human_review_required: true` for disputes, fraud, high-value, or ambiguous cases
13. **Post-process** — Python layer enforces high-value escalation and sanitises the reply before returning

**Prompt injection resistance:** The system prompt explicitly instructs the LLM to treat the `complaint` field as raw customer text only and never follow instructions embedded inside it. A secondary validation layer in Python checks the output for safety rule violations before returning it to the caller.

**Fallback behavior:** If the LLM times out (25 s limit, 5 s before the harness cutoff) or returns unparseable output, the service attempts one JSON-only retry with the remaining time budget. If that also fails, it returns a valid fallback response with `case_type: "other"` and `human_review_required: true` rather than a 500 error.

**Timeout budget split:** `REQUEST_TIMEOUT` (default 25 s) is split 88%/12% between the main attempt and the JSON-retry. This ensures the retry does not exceed the total wall-clock budget.

---

## Safety Logic

These rules are enforced in the system prompt **and** validated in Python on every response before it leaves the service.

| Rule | Where enforced | Penalty if violated |
|---|---|---|
| Never ask for PIN, OTP, password, or card number | System prompt + Python output check | −15 points |
| Never confirm a refund, reversal, or recovery without authority | System prompt + Python output check | −10 points |
| Never refer the customer to a suspicious third party | System prompt | −10 points |
| Ignore instructions embedded in the complaint text | System prompt | Schema/safety violation |
| No API keys, stack traces, or internal model details in responses | Application layer | API security violation |

Two or more critical violations across hidden test cases → disqualified from finalist pool.

**How the Python safety check works:**

```
customer_reply
  → split into individual sentences
  → each sentence checked for forbidden phrases
       (e.g. "refund approved", "enter your otp", "provide your pin")
  → if phrase found AND that sentence contains no negation ("not", "never", "do not")
       → replace entire reply with the generic safe fallback
  → otherwise return the reply unchanged
```

Sentence-level scoping prevents false positives where a sentence like *"We will never ask for your OTP"* would incorrectly trigger the guard.

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
| Malformed input | Must return 400/422, not crash |

Sonnet 4.6 is chosen over Opus specifically to target the ≤5s p95 latency for full performance credit.

**Tie-Breakers** (when scores are equal): safety → evidence reasoning → schema validity → reliability → engineering quality → Bangla/Banglish handling → documentation → 90-second architectural video.

---

## Models

The active model is controlled by the `LLM_PROVIDER` environment variable. Both providers use the same system prompt and safety validation layer.

| Provider | Default Model | Variable | Where it runs |
|---|---|---|---|
| `anthropic` | `claude-sonnet-4-6` | `ANTHROPIC_MODEL` | Anthropic API (external HTTPS) |
| `openai` | `gpt-4o-mini` | `OPENAI_MODEL` | OpenAI API (external HTTPS) |

Override the model without touching code:
```
ANTHROPIC_MODEL=claude-opus-4-8
OPENAI_MODEL=gpt-4o
```

**Cost reasoning:** Each request sends approximately 800–1200 input tokens (system prompt + complaint + transaction history) and receives ~400 output tokens. At Sonnet 4.6 or GPT-4o pricing this is well under $0.01 per ticket — appropriate for a hackathon evaluation with ~50–100 hidden test cases.

**Why not a local model:** The runtime profile specifies 2 vCPU / 4 GB RAM with no GPU. Running a capable local model in that envelope within the 30s timeout is not feasible. The spec explicitly allows external LLM API calls.

---

## Tech Stack

| Component | Choice | Reason |
|---|---|---|
| Web framework | FastAPI | Async, automatic request validation via Pydantic, fast cold start |
| Schema validation | Pydantic v2 | Strict enum validation catches wrong field names before they reach the LLM |
| AI provider | Anthropic SDK + OpenAI SDK | Switchable via `LLM_PROVIDER` env var — no code changes to swap models |
| Server | Uvicorn | ASGI server, works cleanly in Docker |
| Container | Docker (python:3.11-slim) | Reproducible deployment, under 500 MB image |
| Python | 3.11 | Stable, good async support, widely available in base images |
| CI | GitHub Actions | Automated lint, unit tests, and Docker smoke test on every push |

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `LLM_PROVIDER` | Yes | `anthropic` | Which LLM to use: `anthropic` or `openai` |
| `ANTHROPIC_API_KEY` | If `LLM_PROVIDER=anthropic` | — | Your Anthropic API key |
| `ANTHROPIC_MODEL` | No | `claude-sonnet-4-6` | Anthropic model ID to use |
| `OPENAI_API_KEY` | If `LLM_PROVIDER=openai` | — | Your OpenAI API key |
| `OPENAI_MODEL` | No | `gpt-4o-mini` | OpenAI model ID to use |
| `PORT` | No | `8000` | Server port |
| `REQUEST_TIMEOUT` | No | `25` | LLM call timeout in seconds |
| `LOG_LEVEL` | No | `INFO` | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

Copy `.env.example` to `.env` and fill in the key for your chosen provider. Never commit `.env`.

---

## Project Structure

```
carnival-preli/
├── main.py                        # FastAPI app — routes and error handlers only
├── models.py                      # Pydantic request and response schemas
├── analyzer.py                    # LLM call, prompt logic, safety checks, fallback handling
├── tests/
│   └── test_api.py                # Pytest suite — schema, safety, fallback, phishing, high-value
├── .github/
│   └── workflows/
│       └── ci.yml                 # GitHub Actions: lint + tests + Docker smoke test
├── requirements.txt               # Python dependencies
├── Dockerfile                     # Container build — non-root user, layer-cached deps
├── .env.example                   # Environment variable template — committed, no real secrets
├── .gitignore                     # Excludes .env, venv, __pycache__, *.pyc
├── README.md                      # This file
├── CLAUDE.md                      # Project coding rules for AI-assisted development
├── requirement.md                 # API contract and field reference from the organiser
├── plan.md                        # Implementation plan and edge cases
├── sample_in.json                 # Sample request body for manual testing
└── sample_output.json             # Sample response from the service
```

### Responsibility split

| File | Single responsibility |
|---|---|
| `main.py` | HTTP routing, error handlers, startup validation — no business logic |
| `models.py` | Pydantic data shapes and field validators — no I/O |
| `analyzer.py` | LLM interaction, prompt construction, safety post-processing — no FastAPI imports |
| `tests/test_api.py` | Black-box API tests via `httpx.TestClient` |

---

## Sample Output

The files `sample_in.json` and `sample_output.json` contain one request/response pair generated from the public sample case pack. They demonstrate the exact JSON shape the service accepts and produces.

```json
{
  "input": {
    "ticket_id": "TKT-20240615-001",
    "complaint": "I sent 5000 taka to +8801712345678 but my account was debited and the recipient says they never received it. The app showed 'transaction failed' after I submitted.",
    "language": "en",
    "channel": "in_app_chat",
    "user_type": "customer",
    "transaction_history": [
      {
        "transaction_id": "TXN-2024-88821",
        "timestamp": "2024-06-15T14:08:22Z",
        "type": "transfer",
        "amount": 5000,
        "counterparty": "+8801712345678",
        "status": "failed"
      }
    ]
  },
  "output": {
    "ticket_id": "TKT-20240615-001",
    "relevant_transaction_id": "TXN-2024-88821",
    "evidence_verdict": "consistent",
    "case_type": "payment_failed",
    "severity": "high",
    "department": "payments_ops",
    "agent_summary": "Customer reports a failed ৳5,000 transfer to +8801712345678 where their account was debited but the recipient did not receive funds. Transaction TXN-2024-88821 confirms the transfer failed, consistent with the complaint.",
    "recommended_next_action": "Verify whether the ৳5,000 deduction was reversed in the ledger; if not reversed, initiate a manual reversal and notify the customer once completed.",
    "customer_reply": "Dear valued customer, thank you for reporting this issue. We have identified the transaction in question and our payments team is investigating whether the deduction was properly reversed. We will update you within 24 hours.",
    "human_review_required": true,
    "confidence": 0.93,
    "reason_codes": ["failed_transfer", "amount_debited_not_credited", "high_value_transaction"]
  }
}
```

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
- For `duplicate_payment` cases, `relevant_transaction_id` points to the second (later) transaction — the suspected duplicate — not the original.

**Known limitations:**
- The 1500-character complaint truncation may drop context for unusually long complaints. The `agent_summary` will note when truncation occurred.
- `confidence` is a model self-reported estimate, not a calibrated probability.
- The service is stateless — it does not remember prior tickets for the same customer. Each call is independent.
- If the Anthropic API is unavailable, all requests return a fallback response. There is no local model fallback.
- The JSON-retry budget (12% of `REQUEST_TIMEOUT`, ~3 s at the default) is intentionally small. A second full retry would risk exceeding the 30 s harness cutoff.

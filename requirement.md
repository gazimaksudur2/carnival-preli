# QueueStorm Investigator — Requirements

## What I Have to Build

A FastAPI-based AI service that investigates mobile banking complaints using Claude AI.

---

## Endpoints to Implement

### 1. `GET /health`
- Returns: `{"status": "ok"}`
- Purpose: Judge harness uses this to confirm the server is running

### 2. `POST /analyze-ticket`
- Accepts a JSON body with the complaint details
- Sends it to Claude AI for analysis
- Returns a structured JSON response

---

## Input Format (Request Body)

```json
{
  "ticket_id": "string (required)",
  "complaint": "string (required — English, Bangla, or Banglish)",
  "language": "en | bn | mixed (optional)",
  "channel": "in_app_chat | call_center | email | merchant_portal | field_agent (optional)",
  "user_type": "customer | merchant | agent | unknown (optional)",
  "campaign_context": "string (optional)",
  "transaction_history": [
    {
      "transaction_id": "string",
      "timestamp": "string (ISO 8601)",
      "type": "transfer | payment | cash_in | cash_out | settlement | refund",
      "amount": "number (BDT)",
      "counterparty": "string (phone number, merchant ID, or agent ID)",
      "status": "completed | failed | pending | reversed"
    }
  ],
  "metadata": "object (optional)"
}
```

---

## Output Format (Response Body)

```json
{
  "ticket_id": "string (required — must echo request value)",
  "relevant_transaction_id": "string | null (required — ID from history that matches the complaint, or null)",
  "evidence_verdict": "consistent | inconsistent | insufficient_data (required)",
  "case_type": "one of 8 categories — see below (required)",
  "severity": "low | medium | high | critical (required)",
  "department": "one of 6 departments — see below (required)",
  "agent_summary": "string (required — 1-2 sentence case summary for the support agent)",
  "recommended_next_action": "string (required — single operational next step for the agent)",
  "customer_reply": "string (required — safe official reply, must respect safety rules)",
  "human_review_required": "boolean (required — true for disputes, suspicious, high-value, or ambiguous cases)",
  "confidence": "number 0.0–1.0 (optional)",
  "reason_codes": ["array of short label strings (optional)"]
}
```

---

## Case Types (8 categories)

| Case Type | When to Use |
|-----------|-------------|
| `wrong_transfer` | Money sent to wrong person/number |
| `payment_failed` | Payment didn't go through but money deducted |
| `refund_request` | Customer wants money back |
| `duplicate_payment` | Same payment charged twice |
| `merchant_settlement_delay` | Merchant hasn't received the money |
| `agent_cash_in_issue` | Problem with agent-based cash deposit |
| `phishing_or_social_engineering` | Fraud/scam suspected |
| `other` | Doesn't fit any above |

---

## Departments (6 options)

| Department | Handles |
|------------|---------|
| `customer_support` | General issues, queries |
| `dispute_resolution` | Wrong transfer, refund disputes |
| `payments_ops` | Failed payments, technical payment issues |
| `merchant_operations` | Merchant settlement problems |
| `agent_operations` | Agent cash-in/out issues |
| `fraud_risk` | Phishing, social engineering, fraud |

---

## Severity Rules

| Level | When |
|-------|------|
| `low` | Minor issue, no financial loss |
| `medium` | Some inconvenience, small amount involved |
| `high` | Significant financial loss or service disruption |
| `critical` | Large amount, fraud, or VIP customer affected |

---

## Evidence Verdict Logic

Claude must compare the complaint text vs. transaction_history:
- `consistent` → the transaction data supports the complaint (e.g., customer says payment failed and transaction shows "failed")
- `inconsistent` → the data contradicts the complaint (e.g., customer says payment failed but transaction shows "success")
- `insufficient_data` → not enough transaction data to verify the complaint

`relevant_transaction_id` must be the exact `transaction_id` string from the provided history that the complaint refers to, or `null` if no transaction matches.

---

## Safety Rules (CRITICAL — violations = score deduction)

Claude must NEVER:
- Ask the customer for their PIN, OTP, or password (-15 points per violation)
- Confirm or approve an unauthorized refund (-10 points)
- Refer the customer to a suspicious third-party service (-10 points)
- 2+ critical safety violations = disqualified from finalist pool

These rules must be enforced in the Claude prompt (system prompt guardrails).

---

## human_review_required Rules

Set to `true` when any of these apply:
- `case_type` is `wrong_transfer` or any disputed refund
- `case_type` is `phishing_or_social_engineering`
- `evidence_verdict` is `inconsistent` or `insufficient_data`
- Amount is high (≥ 5000 BDT as a safe threshold)
- Anything ambiguous that a human should verify

---

## Files to Create

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app, defines the two endpoints |
| `models.py` | Pydantic schemas for request and response |
| `analyzer.py` | Claude API call logic + safety guardrails |
| `requirements.txt` | Python dependencies |
| `.env.example` | Template for environment variables |
| `Dockerfile` | For containerized deployment |
| `README.md` | Setup instructions for judges |

---

## Environment Variables Needed

```
ANTHROPIC_API_KEY=your_api_key_here
```

---

## Constraints

- Response must arrive within **30 seconds** (judge harness timeout)
- Must use **Claude AI** for the analysis (not rule-based logic)
- Input/output JSON must match the exact schema above — field names must be exact
- Enum values must match exactly (wrong case or alternate spelling = schema violation)
- Server must start cleanly with `docker run` or `uvicorn main:app`

---

## Tech Stack

- **FastAPI** — web framework
- **Pydantic** — request/response validation
- **anthropic** — Python SDK for Claude API
- **uvicorn** — ASGI server
- **Python 3.11+**

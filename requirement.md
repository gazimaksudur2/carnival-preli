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

## API Quality Metrics (from rubric)

| Metric | Expected Standard |
|--------|------------------|
| Health readiness | `GET /health` returns `{"status":"ok"}` within 60s of start |
| Per-request timeout | `POST /analyze-ticket` must complete within 30s |
| p95 latency | Full credit ≤5s · Partial credit ≤15s · Minimal credit ≤30s |
| Failure rate | Valid requests must not return 5xx, invalid JSON, or no response |
| Schema validity | Responses must match required output schema and enum values exactly |
| Malformed input | Return controlled 400 error or safe fallback — never crash |
| Secret handling | No API keys, tokens, stack traces, or sensitive values in repo, logs, or responses |

---

## Scoring Weights

| # | Category | Weight | Stage |
|---|----------|--------|-------|
| 1 | Evidence Reasoning | 35% | Automated |
| 2 | Safety & Escalation | 20% | Automated + Manual |
| 3 | API Contract & Schema | 15% | Automated |
| 4 | Performance & Reliability | 10% | Automated + Manual |
| 5 | Response Quality | 10% | Manual (shortlisted only) |
| 6 | Deployment & Reproducibility | 5% | Automated + Review |
| 7 | Documentation | 5% | Manual (shortlisted only) |

Response Quality and Documentation are only reviewed for shortlisted teams. The first filter is automated.

---

## Safety Penalties

| Violation | Penalty |
|-----------|---------|
| Asks for PIN, OTP, password, full card number | −15 points |
| Confirms refund, reversal, or account recovery without authority | −10 points |
| Instructs customer to contact suspicious third parties | −10 points |
| Two or more critical safety violations | Not eligible for top-40 finalist pool |

---

## Tie-Breakers (in priority order)

1. Safety score and absence of critical violations
2. Evidence reasoning score
3. API/schema validity
4. API reliability, timeout behaviour, deployment stability
5. Exceptional implementation (cost-aware model, caching, monitoring, robust fallback)
6. Bangla/Banglish handling quality — local-language robustness matters when scores are close
7. Documentation quality and manual verification results
8. 90-second architectural overview video

---

## Bangla / Banglish Handling

Complaints may arrive in English, Bangla, or Banglish. The service must:
- Analyze the complaint correctly regardless of language
- Always return the JSON response fields in English
- Not apply any preprocessing or transliteration — Claude handles multilingual input natively
- This is a tie-breaker criterion when scores are close — quality matters here

---

## Tech Stack

- **FastAPI** — web framework
- **Pydantic** — request/response validation
- **anthropic** — Python SDK for Claude API
- **uvicorn** — ASGI server
- **Python 3.11+**

---

## Testing Checklist Before Submission

Run every item below before submitting. All are required.

| Check | Required |
|---|---|
| `GET /health` returns `{"status":"ok"}` | Yes |
| `POST /analyze-ticket` accepts sample JSON | Yes |
| Response contains all required fields | Yes |
| Enum values match the problem statement exactly (case-sensitive) | Yes |
| Service handles empty or missing `transaction_history` without crashing | Yes |
| Service handles malformed or non-critical missing fields without crashing | Yes |
| `customer_reply` does not ask for PIN, OTP, password, or card number | Yes |
| `customer_reply` does not promise refund, reversal, recovery, or account unblock | Yes |
| Endpoint responds within 30 seconds | Yes |
| Docker image builds and runs with `--env-file judging.env` | Yes |
| `GET /health` responds within 60 seconds of container start | Yes |
| README is complete | Yes |
| `sample_output.json` is present in the repository | Yes |
| No real secrets committed anywhere in the repository | Yes |

---

## Submission Form Checklist

All fields required in the submission form:

| Field | Required | Notes |
|---|---|---|
| Team name and team ID | Yes | Use registered team information |
| GitHub repository URL | Yes | Public, or private with `bipulhf` added as collaborator |
| Submission path | Yes | Live URL / Docker fallback / Code-only |
| Public endpoint base URL | If live URL | e.g. `https://your-service.example.com` |
| Docker build/run command | If Docker fallback | Include `--env-file` usage |
| Required environment variable names | If applicable | Names only — not real values |
| Secrets for judging | Only if needed | Use the private form field, never GitHub |
| Sample request and sample response | Yes | Can be in README or `sample_output.json` |
| AI/model usage explanation | Yes | Which model, where it runs, why |
| Safety logic explanation | Yes | How PIN/OTP/refund guardrails are enforced |
| Known limitations | Yes | Be honest about edge cases and failure modes |
| No real customer data confirmation | Yes | Only synthetic data used |
| No secrets committed confirmation | Yes | Written confirmation required |

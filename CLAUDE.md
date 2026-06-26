# Claude Instructions — QueueStorm Investigator

This is a **Python / FastAPI** project that uses the **Anthropic Claude API** to analyze mobile banking complaints. These rules apply to every task. Follow them without being asked.

---

## Project Stack

- **Language:** Python 3.12
- **Framework:** FastAPI + Uvicorn
- **AI:** Anthropic SDK (`anthropic`) or OpenAI SDK (`openai`) — switched via `LLM_PROVIDER` env var
- **Validation:** Pydantic v2
- **Config:** `python-dotenv` — secrets in `.env`, never hardcoded
- **Structure:** flat root — `main.py`, `models.py`, `analyzer.py`

---

## Rule 1 — Consistency Check After Every Change

After any code change, verify nothing is broken:

- **Naming:** Follow the existing Python convention — `snake_case` for variables/functions/files, `PascalCase` for Pydantic models and classes.
- **Imports:** If a function or model is moved or renamed, find and update every file that imports it.
- **Data shape:** If a Pydantic model changes, update every place that constructs, parses, or returns that model.
- **Config:** If a new env variable is added, add it to `.env.example` with a dummy value. Never add it only to `.env`.
- **Before finishing**, confirm no broken references:
  ```bash
  grep -r "old_name" --include="*.py" .
  ```

**Never leave a partial change. Either fully apply it or don't apply it at all.**

---

## Rule 2 — Comments: 2-Line Max, Every Function and Every 5–10 Lines

Write comments that explain **WHY**, not **WHAT**.

### Every function:
```python
# Builds the Claude prompt from ticket fields and transaction history.
# Returns None if complaint is empty — caller must guard against that.
def build_prompt(request: AnalyzeRequest) -> str | None:
```

### Every 5–10 lines of logic:
```python
# Claude returns raw text, not guaranteed JSON — strip markdown fences before parsing.
raw = response.content[0].text.strip().removeprefix("```json").removesuffix("```")
```

### Rules:
- Maximum **2 lines** per comment block
- Never write `# call Claude API` or `# loop through transactions` — these repeat the code
- DO write: hidden constraints, non-obvious API behavior, workarounds, safety guardrails rationale
- If removing the comment would not confuse a future reader, skip it

---

## Rule 3 — No Over-Engineering

Build exactly what is needed for this service. Nothing more.

**Do not:**
- Add abstraction layers or base classes for a single FastAPI app
- Create a `utils/` folder unless logic is genuinely reused in 2+ places
- Add retry logic, circuit breakers, or queuing unless the spec explicitly requires it
- Use async where sync is fine — FastAPI handles the thread pool
- Add config classes or settings objects when `os.getenv()` is sufficient

**Do:**
- Keep `main.py`, `models.py`, `analyzer.py` as the three source files unless a fourth is clearly justified
- Solve problems directly — a 5-line function beats a class hierarchy

---

## Rule 4 — API Design: Match the Spec Exactly

The judge harness tests exact response shapes. Do not deviate.

- `GET /health` → `{"status": "ok"}` — nothing else
- `POST /analyze-ticket` → return the full `AnalyzeResponse` shape defined in `models.py`
- Status codes: `200` for success, `422` for Pydantic validation failures (FastAPI default), `500` for unhandled errors
- Never change a field name, type, or optionality in a response model without checking the spec in `requirement.md`
- All timestamps in ISO 8601: `"2024-06-04T14:30:00Z"`

---

## Rule 5 — Pydantic Models: Single Responsibility

Each model in `models.py` owns exactly one shape.

- `TransactionItem` — one transaction row, nothing else
- `AnalyzeRequest` — the full POST body
- `AnalyzeResponse` — the full response shape
- Do not add business logic inside models — validators are fine, side effects are not
- Use `Literal` and `Enum` for fields with fixed allowed values (`case_type`, `severity`, `channel`, etc.)
- If a model exceeds ~30 fields, ask whether it should be split

---

## Rule 6 — Security: Never Trust, Always Validate

- `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` live in `.env` only — never in source code, not even in comments
- `.env` is in `.gitignore` — never commit it
- `.env.example` must always have dummy values for every env var, including both API keys
- Never log the API key, complaint text containing PII, or full request bodies
- Validate all inputs via Pydantic at the FastAPI boundary — never access raw request body without a model
- Never pass complaint text into shell commands or file paths
- The Claude system prompt must include safety guardrails: never ask for PIN/OTP, never approve refunds directly, no third-party referrals

---

## Rule 7 — Error Handling: Explicit, Informative, Never Silent

**Never do this:**
```python
try:
    result = call_claude(request)
except Exception:
    pass  # silent — production incident waiting to happen
```

**Always do this:**
```python
# Anthropic API errors are operational — log and return a 500 with a safe message.
try:
    result = call_claude(request)
except anthropic.APIError as e:
    logger.error("Claude API call failed", extra={"ticket_id": request.ticket_id, "error": str(e)})
    raise HTTPException(status_code=500, detail="Analysis service unavailable")
```

**Rules:**
- Every `except` block must log, handle, or reraise — never swallow silently
- Never expose raw exception messages or stack traces in API responses
- Use FastAPI's global exception handler for unexpected 500s
- Distinguish: `anthropic.APIError` (operational) vs `json.JSONDecodeError` from Claude's response (programmer/prompt error — log the raw response for debugging)
- Error response shape: `{"detail": "human-readable message"}` — FastAPI's default, keep it consistent

---

## Rule 8 — Naming: Clear Names Over Short Names

- `snake_case` for everything except classes and Pydantic models (`PascalCase`)
- Booleans: `is_fraud`, `has_transaction`, `human_review_required`
- No single-letter variables outside short loops
- No generic names: `data`, `result`, `obj`, `temp` — be specific: `ticket_response`, `parsed_analysis`
- Function names: verb for actions (`build_prompt`, `parse_claude_response`), noun for getters (`get_analyzer`)
- Avoid abbreviations: `msg` → `message`, `cfg` → `config`, `req` → `request`

---

## Rule 9 — LLM API Usage

- The active provider is set by `LLM_PROVIDER` in `.env` — `anthropic` or `openai`. Never hardcode the provider in source.
- Model IDs come from `ANTHROPIC_MODEL` / `OPENAI_MODEL` env vars with defaults in `_call_llm`. Never hardcode a bare model string.
- Set `max_tokens` explicitly on every call — never rely on the default.
- Set a request timeout — the spec says `REQUEST_TIMEOUT=25`, honor it.
- The system prompt is the single source of safety guardrails — do not split guardrail logic between the system prompt and Python code.
- Always parse the LLM response as JSON — if parsing fails, log the raw text and return the safe fallback, not a 500.
- Strip markdown code fences before `json.loads()` — both Claude and GPT-4o sometimes wrap JSON in ` ```json ``` `.
- If `LLM_PROVIDER` is set to an unknown value, the service must exit at startup with a clear error message — not fail silently on the first request.

---

## Rule 10 — Performance: Fast by Default

- FastAPI + Uvicorn is async — use `async def` for route handlers
- The Claude API call is I/O-bound — `await` it, never block the event loop with `time.sleep()` or sync HTTP
- Do not load the Anthropic client on every request — instantiate it once at module level
- Do not log entire transaction histories in production — log only `ticket_id` and error context

---

## Rule 11 — Git and Version Control

- Commit message format: `type(scope): description`
  - Types: `feat`, `fix`, `refactor`, `style`, `docs`, `test`, `chore`
  - Examples: `feat(analyzer): add severity escalation for fraud cases`, `fix(models): make language field optional`
- One commit = one logical change
- Never commit: `.env`, `venv/`, `__pycache__/`, `*.pyc`, `*.pyo`
- Before pushing, run `git diff` to confirm exactly what is going out
- Never force-push to `main`

---

## Rule 12 — File and Folder Structure

Keep this project flat. The structure is:

```
carnival-preli/
├── main.py          # FastAPI app, route definitions only
├── models.py        # Pydantic models only
├── analyzer.py      # Claude API call and response parsing only
├── requirements.txt
├── .env             # real secrets — never committed
├── .env.example     # dummy values — committed
├── .gitignore
├── README.md
└── Dockerfile       # if needed
```

- `main.py` handles HTTP only — no business logic, no Claude calls
- `analyzer.py` handles Claude interaction only — no FastAPI imports
- `models.py` holds data shapes only — no I/O
- If any file exceeds 300 lines, ask whether it is doing too much
- Do not add folders unless a fourth source file forces it

---

## Rule 13 — Communication and Responses

**Before writing code:**
- If the task is ambiguous, ask one focused question — don't guess wrong and do a lot of work in the wrong direction
- If the task is clear, just do it

**While working:**
- One-sentence update when something unexpected is found: "The `analyzer.py` doesn't exist yet — creating it now."
- If a blocker is hit, say what it is and what the options are

**After finishing:**
- One or two sentences: what changed, and what needs attention next
- Don't summarize everything — the diff is readable
- If a change has a side effect worth knowing (e.g., Claude response format assumption), mention it in one line

**Tone:**
- Direct and concise — no "Certainly!", "Great question!", "Of course!"
- No emojis unless asked
- Explain the WHY, not the basics

---

## General Behavior

- **Read before editing.** Always read the file before making any changes.
- **Small, focused changes.** One logical change per task.
- **Ask before deleting.** Never delete a function without confirming it is unused.
- **Match the existing style.** Don't reformat code that isn't being changed.
- **No TODOs left behind.** If something can't be done now, say so — don't leave `# TODO` in code.
- **No magic strings.** Extract literals into named constants: `MODEL = "claude-sonnet-4-6"`, `DEFAULT_TIMEOUT = 25`.
- **Never run destructive commands without asking.** No `rm -rf`, no DB drops, no `git reset --hard` without confirmation.
- **Environment awareness.** Never run test scripts or seed data against a live environment. Check `ENV` or `.env` before any write operation.
- **Dependency caution.** Don't add a new pip package to solve a problem solvable in 10 lines of stdlib code. Every dependency is a future vulnerability.

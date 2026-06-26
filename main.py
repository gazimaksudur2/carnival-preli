"""QueueStorm Investigator -- FastAPI entry point."""
import asyncio
import logging
import os

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

import anthropic
import openai

from analyzer import analyze_ticket
from models import AnalyzeRequest, AnalyzeResponse


# Load .env once at import time so os.getenv() in analyzer.py sees the same values.
load_dotenv()


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
log = logging.getLogger("queuestorm.main")


def _provider_label() -> str:
    return os.getenv("LLM_PROVIDER", "anthropic").lower()


# Cache the SDK client so it is instantiated once, not per request.
_client_cache: dict[str, object] = {}


def _get_client(provider: str):
    """Return a cached SDK client for the active provider."""
    if provider in _client_cache:
        return _client_cache[provider]
    if provider == "openai":
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
    elif provider == "anthropic":
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
    else:
        # Unknown provider -- treat as fallback-only, no client needed.
        client = None
    _client_cache[provider] = client
    return client


@asynccontextmanager
async def lifespan(app: FastAPI):
    provider = _provider_label()
    env_var = "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY"
    if provider not in ("anthropic", "openai"):
        log.error("startup_unknown_provider provider=%s", provider)
    elif not os.getenv(env_var):
        log.warning("startup_no_api_key provider=%s env=%s (fallback only)", provider, env_var)
    else:
        log.info("startup_ready provider=%s", provider)
    yield


app = FastAPI(
    title="QueueStorm Investigator",
    version="1.0.0",
)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    # Pydantic v2 ctx may carry ValueError objects which are not JSON-serializable — keep only safe fields.
    safe_errors = [
        {"loc": list(err.get("loc", [])), "msg": err.get("msg", ""), "type": err.get("type", "")}
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "error": "VALIDATION_ERROR",
            "message": "Invalid request body. Check required fields and enum values.",
            "details": safe_errors,
            "statusCode": 422,
        },
    )


@app.exception_handler(Exception)
async def global_error_handler(request: Request, exc: Exception):
    # Never expose stack traces or internal error messages to clients.
    log.error("Unhandled exception on %s: %s", request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL_ERROR",
            "message": "An unexpected error occurred. Please try again.",
            "statusCode": 500,
        },
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze-ticket", response_model=AnalyzeResponse)
async def analyze_ticket_endpoint(request: AnalyzeRequest):
    provider = _provider_label()
    client = _get_client(provider)
    log.info(
        "analyze_ticket ticket_id=%s lang=%s history=%d provider=%s",
        request.ticket_id, request.language, len(request.transaction_history), provider,
    )
    # LLM call is sync (Anthropic/OpenAI SDK) — offload to thread pool to keep the event loop free.
    return await asyncio.to_thread(analyze_ticket, client, provider, request)


def _has_api_key() -> bool:
    provider = _provider_label()
    if provider == "openai":
        return bool(os.getenv("OPENAI_API_KEY"))
    return bool(os.getenv("ANTHROPIC_API_KEY"))


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host=host, port=port, log_level=os.getenv("LOG_LEVEL", "info").lower())

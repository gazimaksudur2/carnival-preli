import asyncio
import logging
import os
import sys

import anthropic
import openai
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from analyzer import analyze_ticket
from models import AnalyzeRequest, AnalyzeResponse

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Fail fast at startup rather than surfacing auth errors on every request.
provider = os.getenv("LLM_PROVIDER", "anthropic").lower()

if provider == "anthropic":
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY is not set. Set it in .env or the environment. Exiting.")
        sys.exit(1)
    llm_client = anthropic.Anthropic(api_key=api_key)
elif provider == "openai":
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY is not set. Set it in .env or the environment. Exiting.")
        sys.exit(1)
    llm_client = openai.OpenAI(api_key=api_key)
else:
    logger.error("Unknown LLM_PROVIDER '%s'. Must be 'anthropic' or 'openai'. Exiting.", provider)
    sys.exit(1)

app = FastAPI(
    title="QueueStorm Investigator",
    description="AI-powered mobile banking complaint analysis service",
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
    logger.error("Unhandled exception on %s: %s", request.url.path, exc, exc_info=True)
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
    # LLM call is sync (Anthropic/OpenAI SDK) — offload to thread pool to keep the event loop free.
    return await asyncio.to_thread(analyze_ticket, llm_client, provider, request)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

import logging
import uuid
from typing import Optional, Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.app.config import settings
from backend.app.graph.workflow import weather_bot_graph
from backend.app.services.session import session_manager

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Deterministic weather-based safety advisory using LangGraph + SOPs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request / Response models ────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class WeatherFactsResponse(BaseModel):
    temperature_2m: Optional[float] = None
    wind_speed_10m: Optional[float] = None
    wind_gusts_10m: Optional[float] = None
    precipitation: Optional[float] = None
    precipitation_probability: Optional[float] = None
    uv_index: Optional[float] = None
    weather_code: Optional[int] = None
    weather_condition: Optional[str] = None
    location: Optional[str] = None
    time_scope: Optional[str] = None


class ChatResponse(BaseModel):
    session_id: str
    response: str
    sop_id: Optional[str] = None
    sop_name: Optional[str] = None
    severity: Optional[str] = None
    error_type: Optional[str] = None
    fallback_used: bool = False
    decision_trace: list[str] = []
    weather_facts: Optional[WeatherFactsResponse] = None


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "env": settings.APP_ENV,
        "llm_provider": settings.LLM_PROVIDER,
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint.

    Passes the user message and session_id into the LangGraph workflow.
    All safety decisions are made by the deterministic SOP engine inside the graph.
    FastAPI only routes the request and serialises the result.
    """
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Message must not be empty.")

    session_id = request.session_id or str(uuid.uuid4())

    initial_state: dict[str, Any] = {
        "session_id": session_id,
        "user_query": request.message.strip(),
        "intent": None,
        "location": None,
        "weather_facts": None,
        "advisory": None,
        "matched_sops": [],
        "selected_sop": None,
        "decision_trace": [],
        "error_type": None,
        "error_message": None,
        "final_response": None,
        "is_validated": False,
        "fallback_used": False,
    }

    try:
        result = await weather_bot_graph.ainvoke(initial_state)
    except Exception as exc:
        logger.exception("LangGraph workflow raised an unhandled error")
        raise HTTPException(status_code=500, detail=f"Internal workflow error: {str(exc)}")

    final_response = result.get("final_response") or ""
    if not final_response:
        final_response = (
            "I was unable to generate a response. "
            "Please try again or rephrase your question."
        )

    sop = result.get("selected_sop")
    facts = result.get("weather_facts")

    weather_facts_out: Optional[WeatherFactsResponse] = None
    if facts:
        weather_facts_out = WeatherFactsResponse(
            temperature_2m=facts.temperature_2m,
            wind_speed_10m=facts.wind_speed_10m,
            wind_gusts_10m=facts.wind_gusts_10m,
            precipitation=facts.precipitation,
            precipitation_probability=facts.precipitation_probability,
            uv_index=facts.uv_index,
            weather_code=facts.weather_code,
            weather_condition=facts.weather_condition,
            location=facts.location,
            time_scope=facts.time_scope,
        )

    trace = result.get("decision_trace") or []
    trace_strings: list[str] = [str(t) for t in trace]

    return ChatResponse(
        session_id=session_id,
        response=final_response,
        sop_id=sop.sop_id if sop else None,
        sop_name=sop.name if sop else None,
        severity=sop.severity if sop else None,
        error_type=result.get("error_type"),
        fallback_used=bool(result.get("fallback_used")),
        decision_trace=trace_strings,
        weather_facts=weather_facts_out,
    )


@app.delete("/session/{session_id}")
async def clear_session(session_id: str):
    """Clear the conversation context for a session."""
    session_manager.clear(session_id)
    return {"status": "cleared", "session_id": session_id}


# ─── Exception handlers ───────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception in request %s", request.url)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred. Please try again."},
    )

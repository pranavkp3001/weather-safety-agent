import logging
from typing import Any
from backend.app.graph.state import AgentState
from backend.app.services.geocoding import GeocodingService, GeocodingError
from backend.app.services.weather import WeatherService, WeatherServiceError
from backend.app.services.session import session_manager
from backend.app.policies.loader import load_sops
from backend.app.policies.engine import DeterministicSOPEngine
from backend.app.llm.client import get_llm_client
from backend.app.llm.validator import ResponseValidator

logger = logging.getLogger(__name__)

# Initialize singletons for workflow
geocoding_service = GeocodingService()
weather_service = WeatherService()
sop_engine = DeterministicSOPEngine(load_sops())
llm_client = get_llm_client()
response_validator = ResponseValidator()


async def parse_intent_node(state: AgentState) -> dict[str, Any]:
    session_id = state.get("session_id", "default")
    user_query = state.get("user_query", "")

    # Retrieve prior session context if available
    prior_ctx = session_manager.get(session_id)
    prior_dict = {}
    if prior_ctx:
        prior_dict = {
            "last_location": prior_ctx.location.name if prior_ctx.location else None,
            "last_activity": prior_ctx.activity,
            "last_category": prior_ctx.category,
        }

    intent = await llm_client.extract_intent(user_query, prior_dict)
    return {"intent": intent}


async def resolve_session_context_node(state: AgentState) -> dict[str, Any]:
    session_id = state.get("session_id", "default")
    intent = state.get("intent")
    prior_ctx = session_manager.get(session_id)

    # 1. Resolve Location: Query takes precedence; otherwise inherit from session
    resolved_location = None
    if intent and intent.location:
        try:
            resolved_location = await geocoding_service.geocode(intent.location)
        except GeocodingError as e:
            logger.error(f"Geocoding error for '{intent.location}': {e}")
            return {
                "location": None,
                "error_type": "location_error",
                "error_message": f"Could not resolve location '{intent.location}'."
            }
    elif prior_ctx and prior_ctx.location:
        resolved_location = prior_ctx.location

    # If non-outdoor query (e.g. painting bedroom), we don't need location
    if intent and not intent.is_outdoor_query:
        return {
            "location": None,
            "error_type": "no_sop",
            "error_message": "Not an outdoor safety query."
        }

    # If location could not be determined
    if not resolved_location:
        return {
            "location": None,
            "error_type": "location_error",
            "error_message": "No valid location specified or remembered from session."
        }

    # 2. Resolve Activity & Category from session if missing in current turn
    if intent:
        if not intent.activity and prior_ctx and prior_ctx.activity:
            intent.activity = prior_ctx.activity
        if not intent.category and prior_ctx and prior_ctx.category:
            intent.category = prior_ctx.category

    # Update session context (strictly WITHOUT weather facts)
    session_manager.update_context(
        session_id=session_id,
        location=resolved_location,
        activity=intent.activity if intent else None,
        category=intent.category if intent else None,
        time_reference=intent.time_reference if intent else None
    )

    return {
        "location": resolved_location,
        "intent": intent,
        "error_type": None
    }


async def handle_location_error_node(state: AgentState) -> dict[str, Any]:
    err_msg = (
        "I couldn't resolve the location mentioned in your request. "
        "Please specify a valid city or place name so I can fetch live weather data."
    )
    return {
        "final_response": err_msg,
        "error_type": "location_error",
        "is_validated": True,
        "fallback_used": True
    }


async def fetch_weather_node(state: AgentState) -> dict[str, Any]:
    loc = state.get("location")
    intent = state.get("intent")
    advisory = state.get("advisory")

    if not loc:
        return {
            "error_type": "location_error",
            "error_message": "Missing location."
        }

    time_ref = intent.time_reference if intent else None

    try:
        facts = await weather_service.fetch_weather(
            location_name=loc.name,
            latitude=loc.latitude,
            longitude=loc.longitude,
            time_reference=time_ref,
            advisory=advisory
        )
        return {
            "weather_facts": facts,
            "error_type": None
        }
    except WeatherServiceError as e:
        logger.error(f"Weather fetch error: {e}")
        return {
            "weather_facts": None,
            "error_type": "weather_error",
            "error_message": str(e)
        }


async def handle_weather_error_node(state: AgentState) -> dict[str, Any]:
    err_msg = (
        "I couldn't retrieve reliable live weather data from the weather service for that location. "
        "Because MediBuddy policy forbids guessing or providing advice without verified real-time weather facts, "
        "I cannot evaluate safety right now."
    )
    return {
        "final_response": err_msg,
        "error_type": "weather_error",
        "is_validated": True,
        "fallback_used": True
    }


async def match_sops_node(state: AgentState) -> dict[str, Any]:
    facts = state.get("weather_facts")
    intent = state.get("intent")
    advisory = state.get("advisory")

    if not facts:
        return {
            "matched_sops": [],
            "selected_sop": None,
            "decision_trace": [],
            "error_type": "weather_error"
        }

    activity = intent.activity if intent else None
    category = intent.category if intent else None
    advisory_dict = advisory.to_dict() if advisory else None

    matches = sop_engine.match_all(
        weather_facts=facts.to_facts_dict(),
        activity=activity,
        category=category,
        advisory=advisory_dict
    )

    selected, trace = sop_engine.resolve(matches)

    return {
        "matched_sops": matches,
        "selected_sop": selected,
        "decision_trace": trace,
        "error_type": "no_sop" if not selected else None
    }


async def handle_no_sop_node(state: AgentState) -> dict[str, Any]:
    no_sop_msg = (
        "I don't have an applicable Standard Operating Procedure (SOP) for this activity and weather condition. "
        "MediBuddy policy requires explicit written guidelines before giving advice, so I cannot provide safety guidance for this request."
    )
    return {
        "final_response": no_sop_msg,
        "error_type": "no_sop",
        "is_validated": True,
        "fallback_used": True
    }


async def compose_response_node(state: AgentState) -> dict[str, Any]:
    query = state.get("user_query", "")
    facts = state.get("weather_facts")
    selected_sop = state.get("selected_sop")
    error_msg = state.get("error_message")

    response = await llm_client.compose_response(
        query=query,
        facts=facts,
        selected_sop=selected_sop,
        no_sop=False,
        error_message=error_msg
    )
    return {"final_response": response}


async def validate_response_node(state: AgentState) -> dict[str, Any]:
    raw_response = state.get("final_response", "")
    facts = state.get("weather_facts")
    selected_sop = state.get("selected_sop")
    session_id = state.get("session_id", "default")
    user_query = state.get("user_query", "")

    validation = response_validator.validate(
        response_text=raw_response,
        facts=facts,
        selected_sop=selected_sop,
        no_sop=(selected_sop is None)
    )

    if validation.is_valid:
        final_text = raw_response
        fallback_used = False
    else:
        logger.warning(f"Response validation failed ({validation.reason}). Using deterministic fallback.")
        final_text = validation.fallback_response or raw_response
        fallback_used = True

    # Record turn in session history
    ctx = session_manager.get(session_id)
    if ctx:
        ctx.add_turn("user", user_query)
        ctx.add_turn("assistant", final_text, metadata={"sop_id": selected_sop.sop_id if selected_sop else None})

    return {
        "final_response": final_text,
        "is_validated": True,
        "fallback_used": fallback_used
    }

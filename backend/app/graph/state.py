from typing import TypedDict, Optional, Any
from backend.app.llm.prompts import ParsedIntent
from backend.app.services.geocoding import LocationInfo
from backend.app.services.weather import WeatherFacts, AdvisorySignal
from backend.app.policies.models import SOPMatch


class AgentState(TypedDict):
    session_id: str
    user_query: str

    # Extracted intent
    intent: Optional[ParsedIntent]

    # Resolved location
    location: Optional[LocationInfo]

    # Weather facts and external advisory signal
    weather_facts: Optional[WeatherFacts]
    advisory: Optional[AdvisorySignal]

    # SOP Policy evaluations
    matched_sops: list[SOPMatch]
    selected_sop: Optional[SOPMatch]
    decision_trace: list[dict[str, Any]]

    # Error tracking
    error_type: Optional[str]  # "location_error", "weather_error", "no_sop"
    error_message: Optional[str]

    # Final response and verification guardrail
    final_response: Optional[str]
    is_validated: bool
    fallback_used: bool

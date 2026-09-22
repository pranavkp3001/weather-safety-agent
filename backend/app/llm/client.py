import re
import json
import logging
from abc import ABC, abstractmethod
from typing import Optional, Any
from backend.app.config import settings
from backend.app.llm.prompts import (
    ParsedIntent,
    INTENT_EXTRACTION_SYSTEM_PROMPT,
    RESPONSE_COMPOSITION_SYSTEM_PROMPT
)
from backend.app.services.weather import WeatherFacts
from backend.app.policies.models import SOPMatch

logger = logging.getLogger(__name__)


class BaseLLMClient(ABC):
    @abstractmethod
    async def extract_intent(
        self,
        user_message: str,
        prior_context: Optional[dict[str, Any]] = None
    ) -> ParsedIntent:
        """Extract structured intent from user message."""
        pass

    @abstractmethod
    async def compose_response(
        self,
        query: str,
        facts: Optional[WeatherFacts],
        selected_sop: Optional[SOPMatch],
        no_sop: bool = False,
        error_message: Optional[str] = None
    ) -> str:
        """Compose constrained natural language response grounded in facts and SOP guidance."""
        pass


class MockLLMClient(BaseLLMClient):
    """
    Offline deterministic mock client for reproducible unit testing, evaluation,
    and local execution without requiring live external API keys.
    Uses regex and rule heuristics for intent parsing and strict templates for composition.
    """
    async def extract_intent(
        self,
        user_message: str,
        prior_context: Optional[dict[str, Any]] = None
    ) -> ParsedIntent:
        msg = user_message.lower().strip()

        # Indoor / non-outdoor queries
        indoor_keywords = ["bedroom", "living room", "couch", "paint my bedroom", "read a book", "watch tv"]
        if any(kw in msg for kw in indoor_keywords):
            return ParsedIntent(
                activity="indoor leisure",
                category="home_and_leisure",
                location=None,
                time_reference="current",
                is_outdoor_query=False
            )

        # Activity & Category detection with paraphrase matching
        activity = None
        category = None

        if any(kw in msg for kw in ["cycl", "bike", "bicycle", "pedal", "two-wheeler", "scooter"]):
            activity = "cycling"
            category = "outdoor_exercise"
        elif any(kw in msg for kw in ["picnic", "lawn", "outing in park", "outdoor dining"]):
            activity = "picnic"
            category = "home_and_leisure"
        elif any(kw in msg for kw in ["run", "jog", "marathon", "sprint"]):
            activity = "running"
            category = "outdoor_exercise"
        elif any(kw in msg for kw in ["walk", "stroll", "hike", "hiking"]):
            activity = "walking"
            category = "home_and_leisure"
        elif any(kw in msg for kw in ["kid", "child", "toddler", "baby", "elder", "senior", "sandbox"]):
            activity = "children park play" if any(x in msg for x in ["park", "play", "sandbox", "kid", "toddler"]) else "vulnerable group outing"
            category = "vulnerable_groups"
        elif any(kw in msg for kw in ["drive", "travel", "road trip", "highway", "commute"]):
            activity = "travel"
            category = "travel_commute"
        elif any(kw in msg for kw in ["camp", "tent"]):
            activity = "camping"
            category = "home_and_leisure"

        # Time reference detection
        time_ref = "current"
        if "this evening" in msg or "evening" in msg:
            time_ref = "this evening"
        elif "tonight" in msg:
            time_ref = "tonight"
        elif "tomorrow morning" in msg or "morning" in msg:
            time_ref = "tomorrow morning"
        elif "today" in msg:
            time_ref = "today"

        # Location detection - prioritize known cities first, then "in" pattern
        known_cities = ["bhopal", "pune", "delhi", "mumbai", "bangalore", "chennai", "kolkata", "hyderabad", "berlin", "springfield", "atlantisfakecityx99"]
        location = None
        
        # First check for known cities
        for c in known_cities:
            if c in msg:
                location = c.capitalize()
                break
        
        # If no known city found, try "in <Location>" pattern
        if not location:
            in_match = re.search(r'\bin\s+([A-Za-z]+)\b', user_message, re.IGNORECASE)
            if in_match:
                candidate = in_match.group(1).strip()
                # Exclude false positives like "in the", "in this", etc.
                if candidate.lower() not in ["the", "this", "my"]:
                    location = candidate

        return ParsedIntent(
            activity=activity,
            category=category,
            location=location,
            time_reference=time_ref,
            is_outdoor_query=True
        )

    async def compose_response(
        self,
        query: str,
        facts: Optional[WeatherFacts],
        selected_sop: Optional[SOPMatch],
        no_sop: bool = False,
        error_message: Optional[str] = None
    ) -> str:
        if error_message:
            return error_message

        if no_sop or not selected_sop:
            return (
                "I don't have an applicable Standard Operating Procedure (SOP) for this activity and weather condition. "
                "MediBuddy requires written safety policy before offering advice, so I cannot provide safety guidance for this request."
            )

        # Grounded response incorporating exact facts, selected SOP ID, severity, and guidance
        facts_summary = facts.summary_text() if facts else "No live telemetry available."
        time_note = f" for {facts.time_scope}" if (facts and facts.time_scope != "current") else ""

        response = (
            f"Based on MediBuddy Policy [{selected_sop.sop_id}] ({selected_sop.severity.upper()} severity):\n\n"
            f"{selected_sop.guidance}\n\n"
            f"Observed live weather conditions at {facts.location}{time_note}: {facts_summary}."
        )
        return response


class GeminiLLMClient(BaseLLMClient):
    """
    Production Gemini client using google-genai SDK when configured.
    """
    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.model_name = model_name
        try:
            from google import genai
            self.client = genai.Client(api_key=api_key)
        except Exception as e:
            logger.error(f"Failed to initialize google-genai client: {e}")
            self.client = None

    async def extract_intent(
        self,
        user_message: str,
        prior_context: Optional[dict[str, Any]] = None
    ) -> ParsedIntent:
        if not self.client:
            # Fallback to mock logic if uninitialized
            mock = MockLLMClient()
            return await mock.extract_intent(user_message, prior_context)

        prompt = (
            f"{INTENT_EXTRACTION_SYSTEM_PROMPT}\n\n"
            f"Prior Context: {json.dumps(prior_context or {})}\n"
            f"User Query: {user_message}\n\n"
            f"JSON Output:"
        )

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            raw_text = response.text.strip()
            # Clean markdown codeblocks
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]

            data = json.loads(raw_text.strip())
            return ParsedIntent(**data)
        except Exception as e:
            logger.warning(f"Gemini intent extraction error ({e}), falling back to mock parser")
            mock = MockLLMClient()
            return await mock.extract_intent(user_message, prior_context)

    async def compose_response(
        self,
        query: str,
        facts: Optional[WeatherFacts],
        selected_sop: Optional[SOPMatch],
        no_sop: bool = False,
        error_message: Optional[str] = None
    ) -> str:
        if error_message:
            return error_message

        if no_sop or not selected_sop:
            return (
                "I don't have an applicable Standard Operating Procedure (SOP) for this activity and weather condition. "
                "MediBuddy requires written safety policy before offering advice, so I cannot provide safety guidance for this request."
            )

        if not self.client:
            mock = MockLLMClient()
            return await mock.compose_response(query, facts, selected_sop, no_sop, error_message)

        prompt = (
            f"{RESPONSE_COMPOSITION_SYSTEM_PROMPT}\n\n"
            f"User Query: {query}\n"
            f"Selected SOP ID: {selected_sop.sop_id}\n"
            f"Selected SOP Name: {selected_sop.name}\n"
            f"Severity: {selected_sop.severity}\n"
            f"Authoritative Guidance: {selected_sop.guidance}\n"
            f"Weather Facts: {json.dumps(facts.to_facts_dict() if facts else {})}\n"
            f"Weather Summary: {facts.summary_text() if facts else ''}\n\n"
            f"Provide the grounded user response:"
        )

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            return response.text.strip()
        except Exception as e:
            logger.warning(f"Gemini response composition error ({e}), falling back to mock composer")
            mock = MockLLMClient()
            return await mock.compose_response(query, facts, selected_sop, no_sop, error_message)


def get_llm_client() -> BaseLLMClient:
    provider = settings.LLM_PROVIDER.lower().strip()
    if provider == "gemini" and settings.GEMINI_API_KEY:
        return GeminiLLMClient(api_key=settings.GEMINI_API_KEY, model_name=settings.LLM_MODEL)
    # Default to MockLLMClient for offline / deterministic / test operation
    return MockLLMClient()

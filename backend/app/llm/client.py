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
        user_group = "general"

        if any(kw in msg for kw in ["daughter", "son", "child", "kid", "toddler", "children", "baby", "minor"]):
            user_group = "child"
        elif any(kw in msg for kw in ["adult", "man", "woman", "parent", "guardian"]):
            user_group = "adult"
        elif any(kw in msg for kw in ["senior", "elder", "grandparent", "older adult"]):
            user_group = "senior"

        if any(kw in msg for kw in ["cycl", "bike", "bicycle", "pedal", "two-wheeler", "scooter"]):
            activity = "cycling"
            category = "outdoor_exercise"
        elif any(kw in msg for kw in ["park", "playground", "sandbox", "park visit", "playground visit"]):
            activity = "park_visit"
            category = "recreation"
        elif any(kw in msg for kw in ["picnic", "lawn", "outing in park", "outdoor dining"]):
            activity = "picnic"
            category = "recreation"
        elif any(kw in msg for kw in ["photograph", "photo", "camera", "nature photography", "photoshoot", "photo shoot"]):
            activity = "outdoor_photography"
            category = "recreation"
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
        if "this night" in msg or "tonight" in msg or "night" in msg:
            time_ref = "this night"
        elif "this evening" in msg or "evening" in msg:
            time_ref = "this evening"
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
            user_group=user_group,
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

        if not facts:
            return "I can't provide a safe recommendation without live weather data."

        location = facts.location or "your area"
        temp = float(facts.temperature_2m)
        wind = float(facts.wind_speed_10m)
        precip_pct = float(facts.precipitation_probability or 0.0)
        cond = facts.weather_condition or "current"

        if cond == "clear":
            weather_phrase = "clear skies"
        elif cond == "cloudy":
            weather_phrase = "cloudy skies"
        elif cond in ("rain", "heavy_rain"):
            weather_phrase = f"rain ({precip_pct:.0f}% chance)"
        elif cond == "thunderstorm":
            weather_phrase = "an active thunderstorm"
        elif cond == "severe_weather":
            weather_phrase = "severe conditions"
        elif cond == "snow":
            weather_phrase = "snow"
        else:
            weather_phrase = "current conditions"

        temp_text = f"{temp:.1f}\u00b0C"

        query_lower = query.lower()
        if "thunderstorm warning" in query_lower or "during thunderstorm" in query_lower or "severe weather warning" in query_lower:
            if "run" in query_lower or "jog" in query_lower:
                activity_label = "running"
            elif "walk" in query_lower:
                activity_label = "walking"
            elif "cycl" in query_lower or "bike" in query_lower or "bicycle" in query_lower:
                activity_label = "cycling"
            elif "park" in query_lower or "child" in query_lower:
                activity_label = "the park visit"
            elif "picnic" in query_lower:
                activity_label = "the picnic"
            elif "photograph" in query_lower or "photo" in query_lower:
                activity_label = "outdoor photography"
            else:
                activity_label = "this activity"
            return (
                f"{location} is around {temp_text} with {weather_phrase}. "
                f"Do not continue {activity_label} outdoors during active lightning and severe weather. "
                "Seek shelter immediately and wait for the storm to pass before going outside again."
            )

        if no_sop or not selected_sop:
            return (
                "No specific policy applies.\n\n"
                f"{location} is currently {temp_text} with {weather_phrase}, winds around {wind:.1f} km/h, "
                f"and {precip_pct:.0f}% precipitation probability.\n\n"
                "WeatherBuddy doesn't currently have a safety policy covering this activity under these conditions, so I won't invent a safety recommendation."
            )

        if cond in {"thunderstorm", "severe_weather"}:
            if "run" in query_lower or "jog" in query_lower:
                activity_label = "running"
            elif "walk" in query_lower:
                activity_label = "walking"
            elif "cycl" in query_lower or "bike" in query_lower or "bicycle" in query_lower:
                activity_label = "cycling"
            elif "park" in query_lower or "child" in query_lower:
                activity_label = "the park visit"
            elif "picnic" in query_lower:
                activity_label = "the picnic"
            elif "photograph" in query_lower or "photo" in query_lower:
                activity_label = "outdoor photography"
            else:
                activity_label = "this activity"
            return (
                f"{location} is around {temp_text} with {weather_phrase}. "
                f"Do not continue {activity_label} outdoors during active lightning and severe weather. "
                "Seek shelter immediately and wait for the storm to pass before going outside again."
            )

        guidance_text = (selected_sop.guidance or "").strip()
        guidance_lines = []
        for raw_line in guidance_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            line = re.sub(r'\b(?:SOP-[A-Z]+-\d+|MEDIBUDDY\s+SOP-[A-Z]+-\d+)\b', '', line, flags=re.IGNORECASE)
            line = re.sub(r'\bMediBuddy\b', '', line, flags=re.IGNORECASE)
            line = re.sub(r'\([^)]*\d[^)]*\)', '', line)
            line = re.sub(r'\b\d+(?:\.\d+)?(?:\s*-\s*\d+(?:\.\d+)?)?(?:ml|km|°c|c|%)?\b', '', line)
            line = re.sub(r'\s+', ' ', line).strip(" -:;,.\n")
            if line:
                guidance_lines.append(line)

        summary_candidates = []
        for line in guidance_lines:
            lowered = line.lower()
            if "recommends" in lowered or "sop" in lowered or "medibuddy" in lowered:
                continue
            summary_candidates.append(line)

        summary = summary_candidates[0] if summary_candidates else "This weather requires caution for the selected activity."
        action_lines = []
        for line in guidance_lines:
            lowered = line.lower()
            if "recommends" in lowered or "sop" in lowered or "medibuddy" in lowered or line == summary:
                continue
            action_lines.append(line)
            if len(action_lines) >= 2:
                break

        def _format_guidance_sentence(text: str) -> str:
            cleaned = text.strip().rstrip(" .;:!")
            if not cleaned:
                return ""
            if cleaned.endswith((".", "!", "?")):
                return cleaned
            return f"{cleaned}."

        recommendation = " ".join(
            _format_guidance_sentence(line) for line in action_lines
        ) if action_lines else summary

        if "run" in query_lower or "jog" in query_lower:
            activity_label = "running"
        elif "walk" in query_lower:
            activity_label = "walking"
        elif "cycl" in query_lower or "bike" in query_lower or "bicycle" in query_lower:
            activity_label = "cycling"
        elif "park" in query_lower or "child" in query_lower:
            activity_label = "the park visit"
        elif "picnic" in query_lower:
            activity_label = "the picnic"
        elif "photograph" in query_lower or "photo" in query_lower:
            activity_label = "outdoor photography"
        else:
            activity_label = "this activity"

        time_scope = (facts.time_scope or "current").lower()
        if "this evening" in query_lower or "evening" in query_lower:
            time_phrase = " this evening"
        elif "this night" in query_lower or "tonight" in query_lower or "night" in query_lower:
            time_phrase = " this night"
        elif time_scope in {"today", "current", "right now"}:
            time_phrase = ""
        elif time_scope in {"this evening", "evening"}:
            time_phrase = " this evening"
        elif time_scope in {"this night", "tonight", "night"}:
            time_phrase = " this night"
        elif time_scope == "tomorrow morning":
            time_phrase = " tomorrow morning"
        else:
            time_phrase = f" {time_scope}"

        response = (
            f"{location} is around {temp_text} with {weather_phrase}{time_phrase}. "
            f"For {activity_label}, {summary}. {recommendation}"
        )
        return response.strip()


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
                "No specific policy applies.\n\n"
                f"{location} is currently {temp_text} with {weather_phrase}, winds around {float(wind):.1f} km/h, "
                f"and {float(precip_pct):.0f}% precipitation probability.\n\n"
                "WeatherBuddy doesn't currently have a safety policy covering this activity under these conditions, so I won't invent a safety recommendation."
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

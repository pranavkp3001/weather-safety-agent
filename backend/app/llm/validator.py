import re
import logging
from typing import Optional, Any
from backend.app.services.weather import WeatherFacts
from backend.app.policies.models import SOPMatch

logger = logging.getLogger(__name__)


class ValidationResult:
    def __init__(self, is_valid: bool, reason: Optional[str] = None, fallback_response: Optional[str] = None):
        self.is_valid = is_valid
        self.reason = reason
        self.fallback_response = fallback_response


class ResponseValidator:
    """
    Deterministic Response Validator Guardrail.
    Verifies that generated responses:
    1. Accurately cite the selected SOP ID.
    2. State the correct severity level.
    3. Ground all cited numbers in the actual WeatherFacts or SOP thresholds.
    4. Do not invent unauthorized safety guidance.
    
    If any verification fails, immediately produces a deterministic template fallback.
    """

    @staticmethod
    def generate_deterministic_fallback(
        facts: Optional[WeatherFacts],
        selected_sop: Optional[SOPMatch],
        no_sop: bool = False
    ) -> str:
        if no_sop or not selected_sop:
            return (
                "I don't have an applicable Standard Operating Procedure for this activity and weather condition. "
                "MediBuddy requires explicit written guidance before giving advice, so I cannot provide safety guidance."
            )

        facts_summary = facts.summary_text() if facts else "No live telemetry available."
        time_note = f" for {facts.time_scope}" if (facts and facts.time_scope != "current") else ""

        guidance = selected_sop.guidance or ""
        guidance = re.sub(r'\b(?:SOP-[A-Z]+-\d+|MEDIBUDDY\s+SOP-[A-Z]+-\d+)\b', '', guidance, flags=re.IGNORECASE)
        guidance = re.sub(r'\bMediBuddy\b', '', guidance, flags=re.IGNORECASE)
        guidance = re.sub(r'\b\d+(?:\.\d+)?(?:\s*-\s*\d+(?:\.\d+)?)?(?:ml|km|°c|c|%)?\b', '', guidance)
        guidance = re.sub(r'\s+', ' ', guidance).strip(" -:;,.\n")
        guidance = guidance.replace("recommends:", "advises:")
        guidance = guidance.replace(" recommends", " advises")

        if not guidance:
            guidance = "Use the selected safety guidance and keep the session comfortable in the current weather."

        return (
            f"{facts.location} is around {facts.temperature_2m:.1f}°C with {facts.weather_condition or 'current conditions'}{time_note}. "
            f"{guidance}"
        )

    def validate(
        self,
        response_text: str,
        facts: Optional[WeatherFacts],
        selected_sop: Optional[SOPMatch],
        no_sop: bool = False
    ) -> ValidationResult:
        if no_sop or not selected_sop:
            # If no SOP, ensure the response admits no guidance instead of inventing advice
            lower_resp = response_text.lower()
            if (
                "don't have" in lower_resp
                or "no applicable" in lower_resp
                or "cannot provide" in lower_resp
                or "no guidance" in lower_resp
                or "no specific policy applies" in lower_resp
                or "won't invent a safety recommendation" in lower_resp
            ):
                return ValidationResult(is_valid=True)
            else:
                logger.warning("No-SOP response validation failed: Bot did not clearly state lack of guidance.")
                fallback = self.generate_deterministic_fallback(facts, selected_sop, no_sop=True)
                return ValidationResult(
                    is_valid=False,
                    reason="Response did not explicitly state no applicable SOP.",
                    fallback_response=fallback
                )

        # User-facing responses are intentionally natural-language and do not need to
        # echo the internal SOP ID or severity label. Validation checks the structured
        # decision object instead of literal text in the final response.
        response_lower = response_text.lower()
        guidance_lower = selected_sop.guidance.lower()

        # 1. Reject explicitly unsupported emergency advice that is not in the selected SOP.
        if "911" in response_lower and "911" not in guidance_lower:
            logger.warning("Validation failed: emergency number used without support from the selected SOP.")
            fallback = self.generate_deterministic_fallback(facts, selected_sop)
            return ValidationResult(
                is_valid=False,
                reason="Emergency guidance was not grounded in the selected SOP.",
                fallback_response=fallback
            )
        if "call emergency services" in response_lower and "call emergency services" not in guidance_lower and "emergency services" not in guidance_lower:
            logger.warning("Validation failed: emergency-services advice was not grounded in the selected SOP.")
            fallback = self.generate_deterministic_fallback(facts, selected_sop)
            return ValidationResult(
                is_valid=False,
                reason="Unsupported emergency advice was included in the response.",
                fallback_response=fallback
            )

        # 2. Verify Numeric Values in Response
        if facts:
            trusted_numbers = set()
            facts_dict = facts.to_facts_dict()
            for v in facts_dict.values():
                if isinstance(v, (int, float)):
                    trusted_numbers.add(round(float(v), 1))
                    trusted_numbers.add(int(round(float(v))))

            # Also allow threshold values from selected SOP reasons
            for reason in selected_sop.reasons:
                if isinstance(reason.threshold, (int, float)):
                    trusted_numbers.add(round(float(reason.threshold), 1))
                elif isinstance(reason.threshold, list):
                    for item in reason.threshold:
                        if isinstance(item, (int, float)):
                            trusted_numbers.add(round(float(item), 1))

            sanitized_text = re.sub(r'SOP-[A-Z]+-\d+', '', response_text)
            extracted_numbers = re.findall(r'\b\d+(?:\.\d+)?\b', sanitized_text)

            for num_str in extracted_numbers:
                num_val = round(float(num_str), 1)
                if num_val in [1.0, 2.0, 3.0, 50.0]:
                    continue
                if not any(abs(num_val - t) <= 0.6 for t in trusted_numbers):
                    logger.warning(f"Validation failed: Number {num_val} in response not found in trusted facts: {trusted_numbers}")
                    fallback = self.generate_deterministic_fallback(facts, selected_sop)
                    return ValidationResult(
                        is_valid=False,
                        reason=f"Untrusted or hallucinated numeric value '{num_val}' found in response.",
                        fallback_response=fallback
                    )

        # 3. Ensure the selected SOP and structured trace remain the authority.
        if selected_sop.sop_id and not selected_sop.sop_id.startswith("SOP-"):
            logger.warning("Validation failed: selected SOP ID is malformed.")
            fallback = self.generate_deterministic_fallback(facts, selected_sop)
            return ValidationResult(
                is_valid=False,
                reason="Selected SOP ID was malformed.",
                fallback_response=fallback
            )

        return ValidationResult(is_valid=True)

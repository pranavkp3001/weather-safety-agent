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
                "I don't have an applicable Standard Operating Procedure (SOP) for this activity and weather condition. "
                "MediBuddy requires explicit written guidelines before giving advice, so I cannot provide safety guidance."
            )

        facts_summary = facts.summary_text() if facts else "No live telemetry available."
        time_note = f" for {facts.time_scope}" if (facts and facts.time_scope != "current") else ""

        return (
            f"[{selected_sop.sop_id}] ({selected_sop.severity.upper()} Severity): {selected_sop.guidance}\n\n"
            f"Observed live weather conditions at {facts.location}{time_note}: {facts_summary}."
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
            if "don't have" in lower_resp or "no applicable" in lower_resp or "cannot provide" in lower_resp or "no guidance" in lower_resp:
                return ValidationResult(is_valid=True)
            else:
                logger.warning("No-SOP response validation failed: Bot did not clearly state lack of guidance.")
                fallback = self.generate_deterministic_fallback(facts, selected_sop, no_sop=True)
                return ValidationResult(
                    is_valid=False,
                    reason="Response did not explicitly state no applicable SOP.",
                    fallback_response=fallback
                )

        # 1. Verify SOP ID Citation
        if selected_sop.sop_id not in response_text:
            logger.warning(f"Validation failed: SOP ID {selected_sop.sop_id} not cited in response.")
            fallback = self.generate_deterministic_fallback(facts, selected_sop)
            return ValidationResult(
                is_valid=False,
                reason=f"Selected SOP ID '{selected_sop.sop_id}' was missing from the response.",
                fallback_response=fallback
            )

        # 2. Verify Severity Citation
        if selected_sop.severity.lower() not in response_text.lower():
            logger.warning(f"Validation failed: Severity '{selected_sop.severity}' not mentioned.")
            fallback = self.generate_deterministic_fallback(facts, selected_sop)
            return ValidationResult(
                is_valid=False,
                reason=f"Severity level '{selected_sop.severity}' was not correctly identified.",
                fallback_response=fallback
            )

        # 3. Verify Numeric Values in Response
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

            # Extract numbers mentioned in text (excluding SOP ID digits like 001)
            # Replace SOP IDs first
            sanitized_text = re.sub(r'SOP-[A-Z]+-\d+', '', response_text)
            extracted_numbers = re.findall(r'\b\d+(?:\.\d+)?\b', sanitized_text)

            for num_str in extracted_numbers:
                num_val = round(float(num_str), 1)
                # Ignore common harmless numbers like 1, 2 (ranks) or SPF 50
                if num_val in [1.0, 2.0, 3.0, 50.0]:
                    continue
                # Check against trusted numbers with a 0.5 margin for slight rounding
                if not any(abs(num_val - t) <= 0.6 for t in trusted_numbers):
                    logger.warning(f"Validation failed: Number {num_val} in response not found in trusted facts: {trusted_numbers}")
                    fallback = self.generate_deterministic_fallback(facts, selected_sop)
                    return ValidationResult(
                        is_valid=False,
                        reason=f"Untrusted or hallucinated numeric value '{num_val}' found in response.",
                        fallback_response=fallback
                    )

        return ValidationResult(is_valid=True)

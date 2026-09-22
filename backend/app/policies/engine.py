import logging
from typing import Optional, Any
from backend.app.policies.models import (
    SOPDefinition,
    SOPMatch,
    RuleMatchReason,
    ComparisonRule,
    SeverityLevel,
    SEVERITY_WEIGHTS,
)

logger = logging.getLogger(__name__)

FIELD_ALIASES: dict[str, str] = {
    "temperature": "temperature_2m",
    "wind_speed": "wind_speed_10m",
    "wind_gusts": "wind_gusts_10m",
}


class DeterministicSOPEngine:
    """
    Deterministic SOP (Standard Operating Procedure) matching engine.

    Matches weather facts and activity context against a set of SOPs
    to determine which safety procedures apply. Decision logic is explicit
    and deterministic - no LLM inference involved in safety decisions.

    COMPOSITE_SCORE semantics: the score is the sum of penalties whose
    conditions are provably met by the actual weather facts. A missing
    fact can never contribute a penalty and can never be invented.
    """

    @staticmethod
    def _resolve_fact(weather_facts: dict[str, Any], field: str) -> Any:
        """
        Look up a fact by field name, tolerating generic/Open-Meteo naming
        variants (e.g. "temperature" <-> "temperature_2m").
        """
        if field in weather_facts:
            return weather_facts[field]
        for alias, canonical in FIELD_ALIASES.items():
            if field == alias and canonical in weather_facts:
                return weather_facts[canonical]
            if field == canonical and alias in weather_facts:
                return weather_facts[alias]
        return None

    def __init__(self, sops: list[SOPDefinition]):
        """
        Initialize engine with a set of SOPs.
        
        Args:
            sops: List of SOPDefinition objects to match against
        """
        self.sops = sops
        logger.info(f"DeterministicSOPEngine initialized with {len(sops)} SOPs")

    def match_all(
        self,
        weather_facts: dict[str, Any],
        activity: Optional[str] = None,
        category: Optional[str] = None,
        advisory: Optional[dict[str, Any]] = None,
        user_group: Optional[str] = None,
    ) -> list[SOPMatch]:
        """
        Match all SOPs that apply to current weather and activity context.
        
        Args:
            weather_facts: Dict of weather data (temperature, humidity, air_quality_index, etc.)
            activity: Activity type (e.g., "cycling", "running", "walking")
            category: Activity category (optional, for filtering)
            advisory: Weather advisory signals (optional, for enhanced filtering)
            
        Returns:
            List of SOPMatch objects for all matching SOPs, sorted by severity and priority
        """
        matches: list[SOPMatch] = []

        for sop in self.sops:
            # Check if activity applies to this SOP
            if activity and activity.lower() not in [a.lower() for a in sop.applies_to]:
                continue

            # Check conditions
            matched, composite_score = self._conditions_match(sop.conditions, weather_facts, activity, advisory, user_group)
            if matched:
                # Build reasons for match
                reasons = self._get_match_reasons(sop.conditions, weather_facts, activity, advisory, user_group)

                match = SOPMatch(
                    sop_id=sop.id,
                    name=sop.name,
                    category=sop.category,
                    severity=sop.severity,
                    priority=sop.priority,
                    guidance=sop.guidance,
                    reasons=reasons,
                    composite_score=composite_score,
                    is_exact_activity_match=bool(activity and activity.lower() in [a.lower() for a in sop.applies_to]),
                )
                matches.append(match)

        # Sort by severity (descending) then priority (descending)
        matches.sort(
            key=lambda m: (SEVERITY_WEIGHTS.get(m.severity, 0), m.priority),
            reverse=True,
        )

        logger.debug(f"Matched {len(matches)} SOPs for activity={activity}")
        return matches

    def resolve(self, matches: list[SOPMatch]) -> tuple[Optional[SOPMatch], list[str]]:
        """
        Resolve which single SOP should be selected from matched set.
        
        Decision logic:
        1. Highest severity wins
        2. If same severity, highest priority wins
        3. If no matches, return None
        
        Args:
            matches: List of SOPMatch objects to resolve
            
        Returns:
            Tuple of (selected_sop, decision_trace) where decision_trace
            explains the resolution process
        """
        trace: list[str] = []

        if not matches:
            trace.append("No SOPs matched the weather and activity conditions.")
            return None, trace

        # Matches are already sorted by resolve priority in match_all
        selected = matches[0]
        trace.append(
            f"Selected SOP: {selected.sop_id} ({selected.name}) "
            f"with severity={selected.severity}, priority={selected.priority}"
        )

        if len(matches) > 1:
            trace.append(f"Other matching SOPs (not selected): {len(matches) - 1}")
            for m in matches[1:]:
                trace.append(
                    f"  - {m.sop_id} ({m.name}): "
                    f"severity={m.severity}, priority={m.priority}"
                )

        logger.info(f"Resolved to SOP: {selected.sop_id}")
        return selected, trace

    def _conditions_match(
        self, conditions_block: Any, weather_facts: dict[str, Any], activity: Optional[str], advisory: Optional[dict[str, Any]] = None, user_group: Optional[str] = None
    ) -> tuple[bool, Optional[float]]:
        """
        Evaluate if conditions block matches weather facts.

        Supports three operators:
        - AND: All rules must match
        - OR: At least one rule must match
        - COMPOSITE_SCORE: Composite risk scoring with penalties

        Returns (matched, composite_score) where composite_score is only
        populated for COMPOSITE_SCORE blocks.
        """
        operator = conditions_block.operator

        if operator == "AND":
            # All rules must match
            for rule in conditions_block.rules or []:
                if not self._rule_matches(rule, weather_facts, activity, advisory, user_group):
                    return False, None
            return True, None

        elif operator == "OR":
            # At least one rule must match
            if not conditions_block.rules:
                return False, None
            for rule in conditions_block.rules:
                if self._rule_matches(rule, weather_facts, activity, advisory, user_group):
                    return True, None
            return False, None

        elif operator == "COMPOSITE_SCORE":
            # Composite risk scoring: match when accumulated penalties cross the cutoff
            if not conditions_block.scoring:
                return False, None
            score = self._calculate_composite_score(
                conditions_block.scoring, weather_facts
            )
            threshold = conditions_block.scoring.decision_threshold
            operator_type = threshold.operator
            cutoff = threshold.cutoff

            if operator_type == ">":
                return score > cutoff, score
            elif operator_type == ">=":
                return score >= cutoff, score
            elif operator_type == "<":
                return score < cutoff, score
            elif operator_type == "<=":
                return score <= cutoff, score
            return False, score

        return False, None

    def _rule_matches(
        self, rule: ComparisonRule, weather_facts: dict[str, Any], activity: Optional[str], advisory: Optional[dict[str, Any]] = None, user_group: Optional[str] = None
    ) -> bool:
        """
        Evaluate a single comparison rule against weather facts, advisory metadata, and activity.
        """
        field = rule.field
        operator = rule.operator
        value = rule.value

        # Handle activity field specially
        if field == "activity":
            actual = activity or ""
            if operator == "==":
                return actual.lower() == str(value).lower()
            elif operator == "!=":
                return actual.lower() != str(value).lower()
            elif operator == "in":
                return actual.lower() in [v.lower() for v in value]
            return False

        if field == "user_group":
            actual = (user_group or "general").lower()
            if operator == "==":
                return actual == str(value).lower()
            elif operator == "!=":
                return actual != str(value).lower()
            elif operator == "in":
                return actual in [str(v).lower() for v in value]
            return False

        if advisory and field in advisory:
            actual = advisory[field]
        else:
            # Get actual value from weather facts (missing facts are never invented)
            actual = self._resolve_fact(weather_facts, field)
            if actual is None:
                logger.warning(f"Weather fact field '{field}' not found in weather data or advisory metadata")
                return False

        # Compare based on operator
        if operator == ">":
            return actual > value
        elif operator == ">=":
            return actual >= value
        elif operator == "<":
            return actual < value
        elif operator == "<=":
            return actual <= value
        elif operator == "==":
            return actual == value
        elif operator == "!=":
            return actual != value
        elif operator == "in":
            return actual in value
        elif operator == "between":
            # value should be [min, max]
            if isinstance(value, list) and len(value) == 2:
                return value[0] <= actual <= value[1]
            return False
        elif operator == "outside_range":
            # value should be [min, max]
            if isinstance(value, list) and len(value) == 2:
                return actual < value[0] or actual > value[1]
            return False

        return False

    def _calculate_composite_score(self, scoring_config: Any, weather_facts: dict[str, Any]) -> float:
        """
        Calculate a composite risk score using the configured scoring model.

        The semantics are generic and consistent across all COMPOSITE_SCORE rules:
        - add all matched penalties to produce a risk accumulation total
        - when the YAML threshold is expressed as a remaining-safety comparison
          (for example '<=' or '<'), compare against base_score - penalty_total
        - when the threshold is expressed as a risk-accumulation comparison
          (for example '>' or '>='), compare against penalty_total

        This ensures the base score is never treated as a qualifying match by itself,
        while legitimate composite SOPs still evaluate correctly.
        """
        base_score = float(getattr(scoring_config, "base_score", 0.0) or 0.0)
        penalty_total = 0.0

        for penalty in scoring_config.penalties or []:
            actual = self._resolve_fact(weather_facts, penalty.field)
            if actual is None:
                continue

            if self._penalty_condition_matches(penalty.condition, actual):
                penalty_total += float(penalty.penalty)

        threshold = scoring_config.decision_threshold
        if threshold.operator in {"<", "<="}:
            return max(base_score - penalty_total, 0.0)
        return penalty_total

    def _penalty_condition_matches(self, condition: Any, actual: Any) -> bool:
        """
        Evaluate if a penalty condition is met for a given actual value.
        """
        operator = condition.operator

        if operator == ">":
            return actual > condition.threshold
        elif operator == ">=":
            return actual >= condition.threshold
        elif operator == "<":
            return actual < condition.threshold
        elif operator == "<=":
            return actual <= condition.threshold
        elif operator == "==":
            return actual == condition.value
        elif operator == "!=":
            return actual != condition.value
        elif operator == "between":
            # condition should have min and max
            if condition.min is not None and condition.max is not None:
                return condition.min <= actual <= condition.max
            return False
        elif operator == "outside_range":
            # condition should have min and max
            if condition.min is not None and condition.max is not None:
                return actual < condition.min or actual > condition.max
            return False

        return False

    def _get_match_reasons(
        self,
        conditions_block: Any,
        weather_facts: dict[str, Any],
        activity: Optional[str],
        advisory: Optional[dict[str, Any]] = None,
        user_group: Optional[str] = None,
    ) -> list[RuleMatchReason]:
        """
        Extract and document the specific reasons why an SOP matched.
        """
        reasons: list[RuleMatchReason] = []

        if not conditions_block.rules:
            return reasons

        for rule in conditions_block.rules:
            field = rule.field
            operator = rule.operator
            threshold = rule.value

            if field == "activity":
                actual = activity or ""
                matched = self._rule_matches(rule, weather_facts, activity, advisory, user_group)
            elif field == "user_group":
                actual = (user_group or "general").lower()
                matched = self._rule_matches(rule, weather_facts, activity, advisory, user_group)
            elif advisory and field in advisory:
                actual = advisory[field]
                matched = self._rule_matches(rule, weather_facts, activity, advisory, user_group)
            else:
                actual = self._resolve_fact(weather_facts, field)
                if actual is None:
                    continue
                matched = self._rule_matches(rule, weather_facts, activity, advisory, user_group)

            reason = RuleMatchReason(
                field=field,
                actual=actual,
                operator=operator,
                threshold=threshold,
                matched=matched,
                description=f"{field} {operator} {threshold}",
            )
            reasons.append(reason)

        return reasons

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


class DeterministicSOPEngine:
    """
    Deterministic SOP (Standard Operating Procedure) matching engine.
    
    Matches weather facts and activity context against a set of SOPs
    to determine which safety procedures apply. Decision logic is explicit
    and deterministic - no LLM inference involved in safety decisions.
    """

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
            if self._conditions_match(sop.conditions, weather_facts, activity):
                # Build reasons for match
                reasons = self._get_match_reasons(sop.conditions, weather_facts, activity)

                match = SOPMatch(
                    sop_id=sop.id,
                    name=sop.name,
                    category=sop.category,
                    severity=sop.severity,
                    priority=sop.priority,
                    guidance=sop.guidance,
                    reasons=reasons,
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
        self, conditions_block: Any, weather_facts: dict[str, Any], activity: Optional[str]
    ) -> bool:
        """
        Evaluate if conditions block matches weather facts.
        
        Supports three operators:
        - AND: All rules must match
        - OR: At least one rule must match
        - COMPOSITE_SCORE: Composite scoring with penalties
        """
        operator = conditions_block.operator

        if operator == "AND":
            # All rules must match
            for rule in conditions_block.rules or []:
                if not self._rule_matches(rule, weather_facts, activity):
                    return False
            return True

        elif operator == "OR":
            # At least one rule must match
            if not conditions_block.rules:
                return False
            for rule in conditions_block.rules:
                if self._rule_matches(rule, weather_facts, activity):
                    return True
            return False

        elif operator == "COMPOSITE_SCORE":
            # Composite scoring with penalties
            if not conditions_block.scoring:
                return False
            score = self._calculate_composite_score(
                conditions_block.scoring, weather_facts
            )
            threshold = conditions_block.scoring.decision_threshold
            operator_type = threshold.operator
            cutoff = threshold.cutoff

            if operator_type == ">":
                return score > cutoff
            elif operator_type == ">=":
                return score >= cutoff
            elif operator_type == "<":
                return score < cutoff
            elif operator_type == "<=":
                return score <= cutoff

        return False

    def _rule_matches(
        self, rule: ComparisonRule, weather_facts: dict[str, Any], activity: Optional[str]
    ) -> bool:
        """
        Evaluate a single comparison rule against weather facts and activity.
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

        # Get actual value from weather facts
        if field not in weather_facts:
            logger.warning(f"Weather fact field '{field}' not found in weather data")
            return False

        actual = weather_facts[field]

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
        Calculate composite score with penalties.
        
        Starts with base_score and subtracts penalties where conditions match.
        """
        score = scoring_config.base_score

        for penalty in scoring_config.penalties or []:
            field = penalty.field
            condition = penalty.condition
            penalty_amount = penalty.penalty

            if field not in weather_facts:
                continue

            actual = weather_facts[field]

            # Check penalty condition
            if self._penalty_condition_matches(condition, actual):
                score -= penalty_amount

        return max(0.0, score)  # Score cannot go below 0

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
        self, conditions_block: Any, weather_facts: dict[str, Any], activity: Optional[str]
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
                matched = self._rule_matches(rule, weather_facts, activity)
            else:
                actual = weather_facts.get(field)
                if actual is None:
                    continue
                matched = self._rule_matches(rule, weather_facts, activity)

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

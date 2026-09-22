from typing import Literal, Any, Optional
from pydantic import BaseModel, Field

SeverityLevel = Literal["low", "moderate", "high", "severe"]
SEVERITY_WEIGHTS: dict[SeverityLevel, int] = {
    "low": 1,
    "moderate": 2,
    "high": 3,
    "severe": 4,
}


class ComparisonRule(BaseModel):
    field: str
    operator: Literal[">", ">=", "<", "<=", "==", "!=", "in", "outside_range", "between"]
    value: Any
    unit: Optional[str] = None


class PenaltyCondition(BaseModel):
    operator: Literal[">", ">=", "<", "<=", "==", "!=", "outside_range", "between"]
    threshold: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    value: Optional[Any] = None


class CompositeScoringPenalty(BaseModel):
    field: str
    condition: PenaltyCondition
    penalty: float


class CompositeDecisionThreshold(BaseModel):
    operator: Literal["<", "<=", ">", ">="]
    cutoff: float


class CompositeScoringConfig(BaseModel):
    base_score: float = 100.0
    penalties: list[CompositeScoringPenalty] = Field(default_factory=list)
    decision_threshold: CompositeDecisionThreshold


class ConditionsBlock(BaseModel):
    operator: Literal["AND", "OR", "COMPOSITE_SCORE"]
    rules: Optional[list[ComparisonRule]] = Field(default_factory=list)
    scoring: Optional[CompositeScoringConfig] = None


class SOPDefinition(BaseModel):
    id: str
    name: str
    category: str
    applies_to: list[str]
    severity: SeverityLevel
    priority: int = 50
    conditions: ConditionsBlock
    guidance: str
    source: str


class SOPContainer(BaseModel):
    version: str = "1.0"
    sops: list[SOPDefinition]


class RuleMatchReason(BaseModel):
    field: str
    actual: Any
    operator: str
    threshold: Any
    matched: bool
    description: Optional[str] = None


class SOPMatch(BaseModel):
    sop_id: str
    name: str
    category: str
    severity: SeverityLevel
    priority: int
    guidance: str
    reasons: list[RuleMatchReason]
    composite_score: Optional[float] = None
    is_exact_activity_match: bool = False

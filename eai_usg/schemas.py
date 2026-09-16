from __future__ import annotations

from enum import Enum
from typing import List

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EthicalRequirement(StrictModel):
    id: str
    text: str


class ObligationSupportType(str, Enum):
    explicit = "explicit"
    reasonable_implication = "reasonable_implication"


class RequirementObligation(StrictModel):
    id: str = Field(pattern=r"^O[1-9][0-9]*$")
    text: str
    source_span: str
    support_type: ObligationSupportType


class RequirementAnalysis(StrictModel):
    ethical_objective: str
    stakeholders: List[str]
    obligations: List[RequirementObligation] = Field(min_length=1)
    constraints: List[str]
    ambiguities: List[str]
    unsupported_assumptions_to_avoid: List[str]
    possible_operational_aspects: List[str]


class EUS(StrictModel):
    title: str
    description: str
    work_items: List[str] = Field(
        min_length=1,
        description="Distinct work items that operationalize the ethical requirement.",
    )


class WorkItemTrace(StrictModel):
    work_item_index: int = Field(ge=0)
    obligation_ids: List[str]
    explanation: str


class TraceabilityMap(StrictModel):
    description_obligation_ids: List[str]
    work_items: List[WorkItemTrace]


class TraceabilityResult(StrictModel):
    analysis: RequirementAnalysis
    traceability: TraceabilityMap


class QualityDimension(str, Enum):
    clarity = "clarity"
    completeness = "completeness"
    actionability = "actionability"
    testability = "testability"
    faithfulness = "faithfulness"


class Severity(str, Enum):
    minor = "minor"
    major = "major"


class QualityIssue(StrictModel):
    dimension: QualityDimension
    severity: Severity
    problem: str
    recommended_change: str


class ValidationResult(StrictModel):
    clarity: int = Field(ge=1, le=5)
    completeness: int = Field(ge=1, le=5)
    actionability: int = Field(ge=1, le=5)
    testability: int = Field(ge=1, le=5)
    faithfulness: int = Field(ge=1, le=5)
    issues: List[QualityIssue]


class DeterministicCheckResult(StrictModel):
    passed: bool
    structure_issues: List[str]
    redundancy_issues: List[str]


class TraceabilityCheckResult(StrictModel):
    passed: bool
    issues: List[str]

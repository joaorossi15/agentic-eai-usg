from __future__ import annotations

from enum import Enum
from typing import List

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EthicalRequirement(StrictModel):
    id: str
    text: str


class RequirementAnalysis(StrictModel):
    ethical_objective: str

    stakeholders: List[str]

    explicit_requirements: List[str]

    supported_implications: List[str]

    constraints: List[str]

    ambiguities: List[str]

    unsupported_assumptions_to_avoid: List[str]

    possible_operational_aspects: List[str]


class SupportType(str, Enum):
    explicit = "explicit"
    reasonable_implication = "reasonable_implication"
    unsupported = "unsupported"


class CriterionSupport(StrictModel):
    criterion: str
    support_type: SupportType
    supported_by: List[str]
    explanation: str



class EUS(StrictModel):
    title: str
    description: str

    work_items: List[str] = Field(
        min_length=1,
        description=(
            "Distinct work items or acceptance criteria that operationalize "
            "the ethical requirement."
        ),
    )



class QualityDimension(str, Enum):
    clarity = "clarity"
    completeness = "completeness"
    actionability = "actionability"
    testability = "testability"
    faithfulness = "faithfulness"


class Severity(str, Enum):
    minor = "minor"
    major = "major"


class IssueResolution(str, Enum):
    revision = "revision"
    source_limited = "source_limited"


class QualityIssue(StrictModel):
    dimension: QualityDimension
    severity: Severity

    problem: str

    recommended_change: str

    resolution: IssueResolution


class DeterministicCheckResult(StrictModel):
    passed: bool

    structure_issues: List[str]

    redundancy_issues: List[str]


class ValidationResult(StrictModel):
    semantic_gate_passed: bool

    criterion_support: List[CriterionSupport]

    clarity: int = Field(
        ge=1,
        le=5,
    )

    completeness: int = Field(
        ge=1,
        le=5,
    )

    actionability: int = Field(
        ge=1,
        le=5,
    )

    testability: int = Field(
        ge=1,
        le=5,
    )

    faithfulness: int = Field(
        ge=1,
        le=5,
    )

    resolved_issues: List[str]

    unresolved_issues: List[str]

    new_issues: List[str]

    issues: List[QualityIssue]

    passed: bool


class RunStatus(str, Enum):
    passed = "passed"

    requires_human_review = (
        "requires_human_review"
    )

    not_validated = "not_validated"


class ReviewReason(str, Enum):
    unresolved_quality_issue = (
        "unresolved_quality_issue"
    )

    source_limitation = (
        "source_limitation"
    )


class RunArtifacts(StrictModel):
    requirement: EthicalRequirement

    workflow_config: str

    model: str

    analysis: RequirementAnalysis | None = None

    initial_draft: EUS

    initial_checks: DeterministicCheckResult

    validation: ValidationResult | None = None

    revised_draft: EUS | None = None

    revised_checks: DeterministicCheckResult | None = None

    final_validation: ValidationResult | None = None

    final_eus: EUS

    status: RunStatus

    review_reason: ReviewReason | None = None

    api_response_ids: List[str] = Field(
        default_factory=list
    )

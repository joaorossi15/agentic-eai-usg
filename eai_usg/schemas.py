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
    stakeholders: List[str]
    ethical_objective: str
    required_behaviors: List[str]
    constraints: List[str]
    verification_targets: List[str]
    ambiguities: List[str]
    unsupported_inferences_to_avoid: List[str]


class EUS(StrictModel):
    title: str
    description: str
    work_items: List[str] = Field(min_length=1)


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


class QualityAssessment(StrictModel):
    clarity: int = Field(ge=1, le=5)
    completeness: int = Field(ge=1, le=5)
    actionability: int = Field(ge=1, le=5)
    testability: int = Field(ge=1, le=5)
    faithfulness: int = Field(ge=1, le=5)
    issues: List[QualityIssue]
    requires_revision: bool


class ValidationResult(StrictModel):
    clarity: int = Field(ge=1, le=5)
    completeness: int = Field(ge=1, le=5)
    actionability: int = Field(ge=1, le=5)
    testability: int = Field(ge=1, le=5)
    faithfulness: int = Field(ge=1, le=5)
    issues: List[QualityIssue]
    passed: bool


class RunArtifacts(StrictModel):
    requirement: EthicalRequirement
    workflow_config: str
    model: str
    analysis: RequirementAnalysis | None = None
    initial_draft: EUS
    critique: QualityAssessment | None = None
    revised_draft: EUS | None = None
    validation: ValidationResult | None = None
    validation_revision: EUS | None = None
    final_validation: ValidationResult | None = None
    final_eus: EUS
    api_response_ids: List[str] = Field(default_factory=list)

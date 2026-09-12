from __future__ import annotations

from .llm import StructuredLLM
from .prompts import (
    ANALYZER,
    GENERATOR_CONTEXTUAL,
    GENERATOR_DIRECT,
    REVISER,
    VALIDATOR,
)
from .schemas import (
    DeterministicCheckResult,
    EUS,
    EthicalRequirement,
    RequirementAnalysis,
    ValidationResult,
)


class Agents:
    def __init__(
        self,
        llm: StructuredLLM,
        quality_threshold: int = 4,
    ):
        self.llm = llm
        self.quality_threshold = quality_threshold


    def analyze(
        self,
        requirement: EthicalRequirement,
    ) -> RequirementAnalysis:

        return self.llm.generate(
            agent_name="requirement_analysis",
            instructions=ANALYZER,
            user_payload={
                "requirement": requirement.model_dump(),
            },
            output_model=RequirementAnalysis,
        )


    def generate(
        self,
        requirement: EthicalRequirement,
        analysis: RequirementAnalysis | None = None,
    ) -> EUS:

        if analysis is None:
            instructions = GENERATOR_DIRECT

            payload = {
                "requirement": requirement.model_dump(),
            }

        else:
            instructions = GENERATOR_CONTEXTUAL

            payload = {
                "requirement": requirement.model_dump(),
                "analysis": analysis.model_dump(),
            }

        return self.llm.generate(
            agent_name="eus_generation",
            instructions=instructions,
            user_payload=payload,
            output_model=EUS,
        )


    def validate(
        self,
        requirement: EthicalRequirement,
        candidate: EUS,
        checks: DeterministicCheckResult,
        analysis: RequirementAnalysis | None = None,
        previous_draft: EUS | None = None,
        previous_feedback: ValidationResult | None = None,
    ) -> ValidationResult:

        payload = {
            "requirement": requirement.model_dump(),
            "candidate_eus": candidate.model_dump(),
            "deterministic_checks": checks.model_dump(),
            "quality_threshold": self.quality_threshold,
        }

        if previous_draft is not None:
            payload["previous_draft"] = (
                previous_draft.model_dump()
            )

        if previous_feedback is not None:
            payload["previous_feedback"] = (
                previous_feedback.model_dump()
            )

        if analysis is not None:
            payload["analysis"] = (
                analysis.model_dump()
            )

        return self.llm.generate(
            agent_name="eus_validation",
            instructions=VALIDATOR,
            user_payload=payload,
            output_model=ValidationResult,
        )


    def revise(
        self,
        requirement: EthicalRequirement,
        draft: EUS,
        feedback: ValidationResult,
        analysis: RequirementAnalysis | None = None,
    ) -> EUS:

        payload = {
            "requirement": requirement.model_dump(),
            "candidate_eus": draft.model_dump(),
            "validation_feedback": feedback.model_dump(),
        }

        if analysis is not None:
            payload["analysis"] = (
                analysis.model_dump()
            )

        return self.llm.generate(
            agent_name="eus_revision",
            instructions=REVISER,
            user_payload=payload,
            output_model=EUS,
        )

from __future__ import annotations

from .llm import StructuredLLM
from .prompts import ANALYZER, GENERATOR_CONTEXTUAL, GENERATOR_DIRECT, REVISER, VALIDATOR
from .schemas import (
    DeterministicCheckResult,
    EUS,
    EthicalRequirement,
    GeneratedEUS,
    RequirementAnalysis,
    Severity,
    TraceabilityCheckResult,
    TraceabilityMap,
    ValidationResult,
)


class Agents:
    def __init__(self, llm: StructuredLLM, quality_threshold: int = 4):
        self.llm = llm
        self.quality_threshold = quality_threshold

    def analyze(self, requirement: EthicalRequirement) -> RequirementAnalysis:
        return self.llm.generate(
            agent_name="requirement_analysis",
            instructions=ANALYZER,
            user_payload={"requirement": requirement.model_dump()},
            output_model=RequirementAnalysis,
        )

    def generate(
        self,
        requirement: EthicalRequirement,
        analysis: RequirementAnalysis,
    ) -> GeneratedEUS:
        return self.llm.generate(
            agent_name="eus_generation",
            instructions=GENERATOR_CONTEXTUAL,
            user_payload={
                "requirement": requirement.model_dump(),
                "analysis": analysis.model_dump(),
            },
            output_model=GeneratedEUS,
        )

    def generate_direct(self, requirement: EthicalRequirement) -> EUS:
        return self.llm.generate(
            agent_name="eus_generation_direct",
            instructions=GENERATOR_DIRECT,
            user_payload={"requirement": requirement.model_dump()},
            output_model=EUS,
        )

    def validate(
        self,
        requirement: EthicalRequirement,
        candidate: EUS,
        checks: DeterministicCheckResult,
        analysis: RequirementAnalysis,
        traceability: TraceabilityMap | None = None,
        traceability_checks: TraceabilityCheckResult | None = None,
        previous_draft: EUS | None = None,
        previous_feedback: ValidationResult | None = None,
    ) -> ValidationResult:
        payload = {
            "requirement": requirement.model_dump(),
            "analysis": analysis.model_dump(),
            "candidate_eus": candidate.model_dump(),
            "deterministic_checks": checks.model_dump(),
            "quality_threshold": self.quality_threshold,
        }

        if traceability is not None:
            payload["traceability"] = traceability.model_dump()

        if traceability_checks is not None:
            payload["traceability_checks"] = traceability_checks.model_dump()

        if previous_draft is not None:
            payload["previous_draft"] = previous_draft.model_dump()

        if previous_feedback is not None:
            payload["previous_feedback"] = previous_feedback.model_dump()

        result = self.llm.generate(
            agent_name="eus_validation",
            instructions=VALIDATOR,
            user_payload=payload,
            output_model=ValidationResult,
        )

        scores = [
            result.clarity,
            result.completeness,
            result.actionability,
            result.testability,
            result.faithfulness,
        ]

        has_major_issue = any(
            issue.severity == Severity.major
            for issue in result.issues
        )

        passed = (
            result.semantic_gate_passed
            and all(score >= self.quality_threshold for score in scores)
            and not has_major_issue
        )

        return result.model_copy(update={"passed": passed})

    def revise(
        self,
        requirement: EthicalRequirement,
        draft: EUS,
        feedback: ValidationResult,
        analysis: RequirementAnalysis,
        traceability: TraceabilityMap | None = None,
        revision_instruction: str | None = None,
    ) -> GeneratedEUS:
        payload = {
            "requirement": requirement.model_dump(),
            "analysis": analysis.model_dump(),
            "candidate_eus": draft.model_dump(),
            "validation_feedback": feedback.model_dump(),
        }

        if traceability is not None:
            payload["traceability"] = traceability.model_dump()

        if revision_instruction is not None:
            payload["revision_instruction"] = revision_instruction

        return self.llm.generate(
            agent_name="eus_revision",
            instructions=REVISER,
            user_payload=payload,
            output_model=GeneratedEUS,
        )

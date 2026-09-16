from __future__ import annotations

from .llm import StructuredLLM
from .prompts import ANALYZER, GENERATOR_DIRECT, REVISER, TRACEABILITY, VALIDATOR
from .schemas import (
    EUS,
    EthicalRequirement,
    RequirementAnalysis,
    TraceabilityMap,
    TraceabilityResult,
    ValidationResult,
)


class Agents:
    def __init__(self, llm: StructuredLLM):
        self.llm = llm

    def _analyze(self, requirement: EthicalRequirement) -> RequirementAnalysis:
        return self.llm.generate(
            agent_name="requirement_analysis",
            instructions=ANALYZER,
            user_payload={"requirement": requirement.model_dump()},
            output_model=RequirementAnalysis,
        )

    def generate(self, requirement: EthicalRequirement) -> EUS:
        return self.llm.generate(
            agent_name="eus_generation",
            instructions=GENERATOR_DIRECT,
            user_payload={"requirement": requirement.model_dump()},
            output_model=EUS,
        )

    def trace(self, requirement: EthicalRequirement, candidate: EUS) -> TraceabilityResult:
        analysis = self._analyze(requirement)

        traceability = self.llm.generate(
            agent_name="eus_traceability",
            instructions=TRACEABILITY,
            user_payload={
                "requirement": requirement.model_dump(),
                "analysis": analysis.model_dump(),
                "candidate_eus": candidate.model_dump(),
            },
            output_model=TraceabilityMap,
        )

        return TraceabilityResult(
            analysis=analysis,
            traceability=traceability,
        )

    def validate(self, requirement: EthicalRequirement, candidate: EUS) -> ValidationResult:
        return self.llm.generate(
            agent_name="eus_validation",
            instructions=VALIDATOR,
            user_payload={
                "requirement": requirement.model_dump(),
                "candidate_eus": candidate.model_dump(),
            },
            output_model=ValidationResult,
        )

    def revise(
        self,
        requirement: EthicalRequirement,
        draft: EUS,
        feedback: ValidationResult,
        revision_instruction: str | None = None,
    ) -> EUS:
        payload = {
            "requirement": requirement.model_dump(),
            "candidate_eus": draft.model_dump(),
            "validation_feedback": feedback.model_dump(),
        }

        if revision_instruction is not None:
            payload["revision_instruction"] = revision_instruction

        return self.llm.generate(
            agent_name="eus_revision",
            instructions=REVISER,
            user_payload=payload,
            output_model=EUS,
        )

from __future__ import annotations

import os

from .agents import Agents
from .llm import StructuredLLM
from .schemas import (
    EUS,
    EthicalRequirement,
    TraceabilityResult,
    ValidationResult,
)


class EAIUSGPipeline:
    def __init__(
        self,
        backend: str | None = None,
        model: str | None = None,
    ):
        self.backend = backend or os.getenv("EAI_BACKEND", "anthropic")
        self.model = model or os.getenv("EAI_MODEL", "claude-fable-5-1")

        self.llm = StructuredLLM(
            backend=self.backend,
            model=self.model,
        )

        self.agents = Agents(self.llm)

    def generate_eus(
        self,
        requirement: EthicalRequirement,
    ) -> EUS:
        return self.agents.generate(requirement)

    def trace_eus(
        self,
        requirement: EthicalRequirement,
        eus: EUS,
    ) -> TraceabilityResult:
        return self.agents.trace(
            requirement=requirement,
            candidate=eus,
        )

    def validate_eus(
        self,
        requirement: EthicalRequirement,
        eus: EUS,
    ) -> ValidationResult:
        return self.agents.validate(
            requirement=requirement,
            candidate=eus,
        )

    def revise_eus(
        self,
        requirement: EthicalRequirement,
        eus: EUS,
        feedback: ValidationResult,
        revision_instruction: str | None = None,
    ) -> EUS:
        if revision_instruction is not None:
            revision_instruction = revision_instruction.strip()

            if not revision_instruction:
                revision_instruction = None

        return self.agents.revise(
            requirement=requirement,
            draft=eus,
            feedback=feedback,
            revision_instruction=revision_instruction,
        )

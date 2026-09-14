from __future__ import annotations

from .agents import Agents
from .checks import run_deterministic_checks
from .llm import StructuredLLM
from .schemas import BackendGenerationArtifacts, EthicalRequirement


class EAIUSGPipeline:
    def __init__(
        self,
        backend: str,
        model: str,
    ):
        self.llm = StructuredLLM(
            backend=backend,
            model=model,
        )
        self.agents = Agents(self.llm)

    def run(
        self,
        requirement: EthicalRequirement,
        repetition: int,
    ) -> BackendGenerationArtifacts:
        response_start = len(self.llm.response_ids)

        eus = self.agents.generate(requirement)
        checks = run_deterministic_checks(eus)

        return BackendGenerationArtifacts(
            requirement=requirement,
            backend=self.llm.backend,
            model=self.llm.model,
            repetition=repetition,
            eus=eus,
            checks=checks,
            api_response_ids=self.llm.response_ids[response_start:],
        )

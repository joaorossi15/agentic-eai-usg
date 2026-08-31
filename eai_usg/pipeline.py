from __future__ import annotations

import os
from enum import Enum

from .agents import Agents
from .llm import StructuredLLM
from .schemas import EthicalRequirement, RunArtifacts


class WorkflowConfig(str, Enum):
    FULL = "full"
    NO_ANALYSIS = "no_analysis"
    NO_CRITIQUE_REVISION = "no_critique_revision"
    NO_VALIDATION = "no_validation"
    SINGLE_PASS = "single_pass"


class EAIUSGPipeline:
    def __init__(self, model: str | None = None, quality_threshold: int | None = None):
        threshold = quality_threshold or int(os.getenv("EAI_VALIDATION_THRESHOLD", "4"))
        self.llm = StructuredLLM(model=model)
        self.agents = Agents(self.llm, quality_threshold=threshold)

    def run(self, requirement: EthicalRequirement, config: WorkflowConfig = WorkflowConfig.FULL) -> RunArtifacts:
        if config == WorkflowConfig.SINGLE_PASS:
            initial = self.agents.generate(requirement, analysis=None)
            return RunArtifacts(
                requirement=requirement,
                workflow_config=config.value,
                model=self.llm.model,
                initial_draft=initial,
                final_eus=initial,
                api_response_ids=list(self.llm.response_ids),
            )

        use_analysis = config != WorkflowConfig.NO_ANALYSIS
        use_critique_revision = config != WorkflowConfig.NO_CRITIQUE_REVISION
        use_validation = config != WorkflowConfig.NO_VALIDATION

        analysis = self.agents.analyze(requirement) if use_analysis else None
        initial = self.agents.generate(requirement, analysis=analysis)
        current = initial

        critique = None
        revised = None
        if use_critique_revision:
            critique = self.agents.critique(requirement, current, analysis=analysis)
            if critique.requires_revision:
                revised = self.agents.revise(requirement, current, critique, analysis=analysis)
                current = revised

        validation = None
        validation_revision = None
        final_validation = None
        if use_validation:
            validation = self.agents.validate(requirement, current, analysis=analysis)

            # Validation is operational only when revision is available:
            # one failed gate can trigger exactly one targeted extra revision.
            if (not validation.passed) and use_critique_revision:
                validation_revision = self.agents.revise(requirement, current, validation, analysis=analysis)
                current = validation_revision
                final_validation = self.agents.validate(requirement, current, analysis=analysis)

        return RunArtifacts(
            requirement=requirement,
            workflow_config=config.value,
            model=self.llm.model,
            analysis=analysis,
            initial_draft=initial,
            critique=critique,
            revised_draft=revised,
            validation=validation,
            validation_revision=validation_revision,
            final_validation=final_validation,
            final_eus=current,
            api_response_ids=list(self.llm.response_ids),
        )

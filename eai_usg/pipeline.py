from __future__ import annotations

import os
from enum import Enum

from .agents import Agents
from .checks import run_deterministic_checks
from .llm import StructuredLLM
from .schemas import (
    EthicalRequirement,
    RunArtifacts,
    RunStatus,
)


class WorkflowConfig(str, Enum):
    FULL = "full"

    NO_ANALYSIS = "no_analysis"

    NO_CRITIQUE_REVISION = "no_critique_revision"
    NO_VALIDATION = "no_validation"

    SINGLE_PASS = "single_pass"


class EAIUSGPipeline:
    def __init__(
        self,
        model: str | None = None,
        quality_threshold: int | None = None,
    ):

        threshold = quality_threshold or int(
            os.getenv(
                "EAI_VALIDATION_THRESHOLD",
                "4",
            )
        )

        self.llm = StructuredLLM(
            model=model,
        )

        self.agents = Agents(
            self.llm,
            quality_threshold=threshold,
        )

    def run(
        self,
        requirement: EthicalRequirement,
        config: WorkflowConfig = WorkflowConfig.FULL,
    ) -> RunArtifacts:

        response_start = len(
            self.llm.response_ids
        )

        if config == WorkflowConfig.SINGLE_PASS:
            initial = self.agents.generate(
                requirement
            )
            initial_checks = run_deterministic_checks(
                initial
            )

            return RunArtifacts(
                requirement=requirement,
                workflow_config=config.value,
                model=self.llm.model,

                initial_draft=initial,
                initial_checks=initial_checks,

                final_eus=initial,

                status=RunStatus.not_validated,

                api_response_ids=(
                    self.llm.response_ids[response_start:]
                ),
            )

        use_analysis = (
            config != WorkflowConfig.NO_ANALYSIS
        )

        use_critique_revision = (
            config
            != WorkflowConfig.NO_CRITIQUE_REVISION
        )

        use_validation = (
            config != WorkflowConfig.NO_VALIDATION
        )

        analysis = (
            self.agents.analyze(requirement)
            if use_analysis
            else None
        )

        initial = self.agents.generate(
            requirement,
            analysis=analysis,
        )

        initial_checks = (
            run_deterministic_checks(initial)
        )

        current = initial
        current_checks = initial_checks

        critique = None
        revised = None
        revised_checks = None

        if use_critique_revision:

            critique = self.agents.critique(
                requirement=requirement,
                draft=current,
                checks=current_checks,
                analysis=analysis,
            )

            if (
                critique.requires_revision
                or not current_checks.passed
            ):

                revised = self.agents.revise(
                    requirement=requirement,
                    draft=current,
                    feedback=critique,
                    analysis=analysis,
                )

                current = revised

                revised_checks = (
                    run_deterministic_checks(
                        current
                    )
                )

                current_checks = revised_checks

        validation = None
        validation_revision = None
        validation_revision_checks = None
        final_validation = None

        if not use_validation:
            status = RunStatus.not_validated

        else:
            previous_draft = (
                initial
                if revised is not None
                else current
            )

            previous_feedback = critique
            validation = self.agents.validate(
                requirement=requirement,
                candidate=current,
                previous_draft=previous_draft,
                previous_feedback=previous_feedback,
                checks=current_checks,
                analysis=analysis,
            )

            if validation.passed:
                status = RunStatus.passed

            elif use_critique_revision:
                before_targeted_revision = current

                validation_revision = (
                    self.agents.revise(
                        requirement=requirement,
                        draft=current,
                        feedback=validation,
                        analysis=analysis,
                    )
                )

                current = validation_revision

                validation_revision_checks = (
                    run_deterministic_checks(
                        current
                    )
                )

                current_checks = (
                    validation_revision_checks
                )

                final_validation = (
                    self.agents.validate(
                        requirement=requirement,
                        candidate=current,
                        previous_draft=(
                            before_targeted_revision
                        ),
                        previous_feedback=validation,
                        checks=current_checks,
                        analysis=analysis,
                    )
                )

                if final_validation.passed:
                    status = RunStatus.passed
                else:
                    status = (
                        RunStatus.requires_human_review
                    )

            else:

                status = (
                    RunStatus.requires_human_review
                )

        return RunArtifacts(
            requirement=requirement,
            workflow_config=config.value,
            model=self.llm.model,

            analysis=analysis,

            initial_draft=initial,
            initial_checks=initial_checks,

            critique=critique,

            revised_draft=revised,
            revised_checks=revised_checks,

            validation=validation,

            validation_revision=validation_revision,
            validation_revision_checks=(
                validation_revision_checks
            ),

            final_validation=final_validation,

            final_eus=current,
            status=status,

            api_response_ids=(
                self.llm.response_ids[response_start:]
            ),
        )

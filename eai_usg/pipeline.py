from __future__ import annotations

import os
from enum import Enum

from .agents import Agents
from .checks import run_deterministic_checks, run_traceability_checks
from .llm import StructuredLLM
from .schemas import (
    EthicalRequirement,
    IssueResolution,
    ReviewReason,
    RunArtifacts,
    RunStatus,
)


def _has_revision_issues(issues) -> bool:
    return any(issue.resolution == IssueResolution.revision for issue in issues)


def _review_reason() -> ReviewReason:
    return ReviewReason.unresolved_quality_issue


class WorkflowConfig(str, Enum):
    FULL = "full"
    SINGLE_PASS = "single_pass"


class EAIUSGPipeline:
    def __init__(
        self,
        model: str | None = None,
        quality_threshold: int | None = None,
    ):
        threshold = (
            quality_threshold
            if quality_threshold is not None
            else int(os.getenv("EAI_VALIDATION_THRESHOLD", "4"))
        )

        self.llm = StructuredLLM(model=model)
        self.agents = Agents(self.llm, quality_threshold=threshold)

    def run(
        self,
        requirement: EthicalRequirement,
        config: WorkflowConfig = WorkflowConfig.FULL,
    ) -> RunArtifacts:
        response_start = len(self.llm.response_ids)

        if config == WorkflowConfig.SINGLE_PASS:
            initial = self.agents.generate_direct(requirement)
            initial_checks = run_deterministic_checks(initial)

            return RunArtifacts(
                requirement=requirement,
                workflow_config=config.value,
                model=self.llm.model,
                analysis=None,
                initial_draft=initial,
                initial_traceability=None,
                initial_checks=initial_checks,
                initial_traceability_checks=None,
                validation=None,
                revised_draft=None,
                revised_traceability=None,
                revised_checks=None,
                revised_traceability_checks=None,
                final_validation=None,
                final_eus=initial,
                final_traceability=None,
                status=RunStatus.not_validated,
                review_reason=None,
                api_response_ids=self.llm.response_ids[response_start:],
            )

        analysis = self.agents.analyze(requirement)

        generated = self.agents.generate(
            requirement=requirement,
            analysis=analysis,
        )

        initial = generated.eus
        initial_traceability = generated.traceability

        initial_checks = run_deterministic_checks(initial)
        initial_traceability_checks = run_traceability_checks(
            analysis=analysis,
            eus=initial,
            traceability=initial_traceability,
        )

        current = initial
        current_traceability = initial_traceability
        current_checks = initial_checks
        current_traceability_checks = initial_traceability_checks

        validation = self.agents.validate(
            requirement=requirement,
            candidate=current,
            traceability=current_traceability,
            previous_draft=None,
            previous_feedback=None,
            checks=current_checks,
            traceability_checks=current_traceability_checks,
            analysis=analysis,
        )

        revised = None
        revised_traceability = None
        revised_checks = None
        revised_traceability_checks = None
        final_validation = None
        review_reason = None

        if (
            validation.passed
            and current_checks.passed
            and current_traceability_checks.passed
        ):
            status = RunStatus.passed

        elif (
            _has_revision_issues(validation.issues)
            or not current_checks.passed
            or not current_traceability_checks.passed
        ):
            before_revision = current

            revised_generated = self.agents.revise(
                requirement=requirement,
                draft=current,
                traceability=current_traceability,
                feedback=validation,
                analysis=analysis,
            )

            revised = revised_generated.eus
            revised_traceability = revised_generated.traceability

            revised_checks = run_deterministic_checks(revised)
            revised_traceability_checks = run_traceability_checks(
                analysis=analysis,
                eus=revised,
                traceability=revised_traceability,
            )

            current = revised
            current_traceability = revised_traceability
            current_checks = revised_checks
            current_traceability_checks = revised_traceability_checks

            final_validation = self.agents.validate(
                requirement=requirement,
                candidate=current,
                traceability=current_traceability,
                previous_draft=before_revision,
                previous_feedback=validation,
                checks=current_checks,
                traceability_checks=current_traceability_checks,
                analysis=analysis,
            )

            if (
                final_validation.passed
                and current_checks.passed
                and current_traceability_checks.passed
            ):
                status = RunStatus.passed
            else:
                status = RunStatus.requires_human_review
                review_reason = _review_reason()

        else:
            status = RunStatus.requires_human_review
            review_reason = _review_reason()

        return RunArtifacts(
            requirement=requirement,
            workflow_config=config.value,
            model=self.llm.model,
            analysis=analysis,
            initial_draft=initial,
            initial_traceability=initial_traceability,
            initial_checks=initial_checks,
            initial_traceability_checks=initial_traceability_checks,
            validation=validation,
            revised_draft=revised,
            revised_traceability=revised_traceability,
            revised_checks=revised_checks,
            revised_traceability_checks=revised_traceability_checks,
            final_validation=final_validation,
            final_eus=current,
            final_traceability=current_traceability,
            status=status,
            review_reason=review_reason,
            api_response_ids=self.llm.response_ids[response_start:],
        )

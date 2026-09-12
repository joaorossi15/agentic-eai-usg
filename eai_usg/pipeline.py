from __future__ import annotations

import os
from enum import Enum

from .agents import Agents
from .checks import run_deterministic_checks
from .llm import StructuredLLM
from .schemas import (
    EthicalRequirement,
    IssueResolution,
    ReviewReason,
    RunArtifacts,
    RunStatus,
)


# ===========================================================================
# Issue helpers
# ===========================================================================


def _has_revision_issues(issues) -> bool:
    """
    Return True when at least one validation issue can legitimately be
    addressed by rewriting the EUS using information already available in
    the source requirement.
    """
    return any(
        issue.resolution == IssueResolution.revision
        for issue in issues
    )


def _only_source_limited_issues(issues) -> bool:
    """
    Return True when at least one issue exists and every remaining issue is
    caused by information missing or underspecified in the source requirement.
    """
    return bool(issues) and all(
        issue.resolution == IssueResolution.source_limited
        for issue in issues
    )


def _review_reason(issues) -> ReviewReason:
    """
    Determine why human review is required.
    """
    if _only_source_limited_issues(issues):
        return ReviewReason.source_limitation

    return ReviewReason.unresolved_quality_issue


# ===========================================================================
# Workflow configurations
# ===========================================================================


class WorkflowConfig(str, Enum):
    FULL = "full"

    NO_ANALYSIS = "no_analysis"

    NO_REVISION = "no_revision"

    NO_VALIDATION = "no_validation"

    SINGLE_PASS = "single_pass"


# ===========================================================================
# Pipeline
# ===========================================================================


class EAIUSGPipeline:
    def __init__(
        self,
        model: str | None = None,
        quality_threshold: int | None = None,
    ):
        threshold = (
            quality_threshold
            if quality_threshold is not None
            else int(
                os.getenv(
                    "EAI_VALIDATION_THRESHOLD",
                    "4",
                )
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

        # ===================================================================
        # Single-pass baseline
        # ===================================================================

        if config == WorkflowConfig.SINGLE_PASS:
            initial = self.agents.generate(
                requirement
            )

            initial_checks = (
                run_deterministic_checks(
                    initial
                )
            )

            return RunArtifacts(
                requirement=requirement,
                workflow_config=config.value,
                model=self.llm.model,

                analysis=None,

                initial_draft=initial,
                initial_checks=initial_checks,

                validation=None,

                revised_draft=None,
                revised_checks=None,

                final_validation=None,

                final_eus=initial,

                status=RunStatus.not_validated,
                review_reason=None,

                api_response_ids=(
                    self.llm.response_ids[
                        response_start:
                    ]
                ),
            )

        # ===================================================================
        # Configure workflow
        # ===================================================================

        use_analysis = (
            config
            != WorkflowConfig.NO_ANALYSIS
        )

        use_revision = (
            config
            != WorkflowConfig.NO_REVISION
        )

        use_validation = (
            config
            != WorkflowConfig.NO_VALIDATION
        )

        # ===================================================================
        # Analysis
        # ===================================================================

        analysis = (
            self.agents.analyze(
                requirement
            )
            if use_analysis
            else None
        )

        # ===================================================================
        # Generation
        # ===================================================================

        initial = self.agents.generate(
            requirement,
            analysis=analysis,
        )

        initial_checks = (
            run_deterministic_checks(
                initial
            )
        )

        current = initial
        current_checks = initial_checks

        # Artifacts that may be populated later
        validation = None

        revised = None
        revised_checks = None

        final_validation = None

        review_reason = None

        # ===================================================================
        # Validation disabled
        # ===================================================================

        if not use_validation:
            return RunArtifacts(
                requirement=requirement,
                workflow_config=config.value,
                model=self.llm.model,

                analysis=analysis,

                initial_draft=initial,
                initial_checks=initial_checks,

                validation=None,

                revised_draft=None,
                revised_checks=None,

                final_validation=None,

                final_eus=current,

                status=RunStatus.not_validated,
                review_reason=None,

                api_response_ids=(
                    self.llm.response_ids[
                        response_start:
                    ]
                ),
            )

        # ===================================================================
        # Initial validation
        # ===================================================================

        validation = self.agents.validate(
            requirement=requirement,
            candidate=current,
            previous_draft=None,
            previous_feedback=None,
            checks=current_checks,
            analysis=analysis,
        )

        # ===================================================================
        # Passed immediately
        # ===================================================================

        if (
            validation.passed
            and current_checks.passed
        ):
            status = RunStatus.passed

        # ===================================================================
        # Validation found something revision can fix
        # ===================================================================

        elif (
            use_revision
            and (
                _has_revision_issues(
                    validation.issues
                )
                or not current_checks.passed
            )
        ):
            before_revision = current

            revised = self.agents.revise(
                requirement=requirement,
                draft=current,
                feedback=validation,
                analysis=analysis,
            )

            revised_checks = (
                run_deterministic_checks(
                    revised
                )
            )

            current = revised
            current_checks = revised_checks

            # ===============================================================
            # One revalidation only
            # ===============================================================

            final_validation = (
                self.agents.validate(
                    requirement=requirement,
                    candidate=current,
                    previous_draft=before_revision,
                    previous_feedback=validation,
                    checks=current_checks,
                    analysis=analysis,
                )
            )

            if (
                final_validation.passed
                and current_checks.passed
            ):
                status = RunStatus.passed

            else:
                status = (
                    RunStatus.requires_human_review
                )

                review_reason = (
                    _review_reason(
                        final_validation.issues
                    )
                )

        # ===================================================================
        # Failed, but revision is disabled or cannot legitimately fix it
        # ===================================================================

        else:
            status = (
                RunStatus.requires_human_review
            )

            review_reason = (
                _review_reason(
                    validation.issues
                )
            )

        # ===================================================================
        # Final artifacts
        # ===================================================================

        return RunArtifacts(
            requirement=requirement,
            workflow_config=config.value,
            model=self.llm.model,

            analysis=analysis,

            initial_draft=initial,
            initial_checks=initial_checks,

            validation=validation,

            revised_draft=revised,
            revised_checks=revised_checks,

            final_validation=final_validation,

            final_eus=current,

            status=status,
            review_reason=review_reason,

            api_response_ids=(
                self.llm.response_ids[
                    response_start:
                ]
            ),
        )

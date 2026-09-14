from __future__ import annotations

import os
from enum import Enum

from .agents import Agents
from .checks import run_deterministic_checks, run_traceability_checks
from .llm import StructuredLLM
from .schemas import (
    EUS,
    EUSRevisionArtifacts,
    EUSValidationArtifacts,
    EthicalRequirement,
    IssueResolution,
    RequirementAnalysis,
    ReviewReason,
    RunArtifacts,
    RunStatus,
    TraceabilityMap,
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
        threshold = quality_threshold if quality_threshold is not None else int(os.getenv("EAI_VALIDATION_THRESHOLD", "4"))
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
            checks=current_checks,
            analysis=analysis,
            traceability=current_traceability,
            traceability_checks=current_traceability_checks,
        )

        revised = None
        revised_traceability = None
        revised_checks = None
        revised_traceability_checks = None
        final_validation = None
        review_reason = None

        if validation.passed and current_checks.passed and current_traceability_checks.passed:
            status = RunStatus.passed

        elif _has_revision_issues(validation.issues) or not current_checks.passed or not current_traceability_checks.passed:
            before_revision = current

            revised_generated = self.agents.revise(
                requirement=requirement,
                draft=current,
                feedback=validation,
                analysis=analysis,
                traceability=current_traceability,
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
                checks=current_checks,
                analysis=analysis,
                traceability=current_traceability,
                traceability_checks=current_traceability_checks,
                previous_draft=before_revision,
                previous_feedback=validation,
            )

            if final_validation.passed and current_checks.passed and current_traceability_checks.passed:
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

    def validate_eus(
        self,
        requirement: EthicalRequirement,
        eus: EUS,
        analysis: RequirementAnalysis | None = None,
        traceability: TraceabilityMap | None = None,
    ) -> EUSValidationArtifacts:
        response_start = len(self.llm.response_ids)

        if traceability is not None and analysis is None:
            raise ValueError("An analysis must be provided when validating an existing traceability map.")

        if analysis is None:
            analysis = self.agents.analyze(requirement)

        checks = run_deterministic_checks(eus)

        traceability_checks = None

        if traceability is not None:
            traceability_checks = run_traceability_checks(
                analysis=analysis,
                eus=eus,
                traceability=traceability,
            )

        validation = self.agents.validate(
            requirement=requirement,
            candidate=eus,
            checks=checks,
            analysis=analysis,
            traceability=traceability,
            traceability_checks=traceability_checks,
        )

        return EUSValidationArtifacts(
            requirement=requirement,
            model=self.llm.model,
            analysis=analysis,
            eus=eus,
            traceability=traceability,
            checks=checks,
            traceability_checks=traceability_checks,
            validation=validation,
            api_response_ids=self.llm.response_ids[response_start:],
        )

    def revise_eus(
        self,
        requirement: EthicalRequirement,
        eus: EUS,
        revision_instruction: str | None = None,
        analysis: RequirementAnalysis | None = None,
        traceability: TraceabilityMap | None = None,
    ) -> EUSRevisionArtifacts:
        response_start = len(self.llm.response_ids)

        if traceability is not None and analysis is None:
            raise ValueError("An analysis must be provided when revising from an existing traceability map.")

        if revision_instruction is not None:
            revision_instruction = revision_instruction.strip()

            if not revision_instruction:
                revision_instruction = None

        if analysis is None:
            analysis = self.agents.analyze(requirement)

        original_checks = run_deterministic_checks(eus)

        traceability_checks = None

        if traceability is not None:
            traceability_checks = run_traceability_checks(
                analysis=analysis,
                eus=eus,
                traceability=traceability,
            )

        initial_validation = self.agents.validate(
            requirement=requirement,
            candidate=eus,
            checks=original_checks,
            analysis=analysis,
            traceability=traceability,
            traceability_checks=traceability_checks,
        )

        if initial_validation.passed and original_checks.passed and revision_instruction is None:
            raise ValueError("The EUS passed validation and no revision instruction was provided.")

        revised_generated = self.agents.revise(
            requirement=requirement,
            draft=eus,
            feedback=initial_validation,
            analysis=analysis,
            traceability=traceability,
            revision_instruction=revision_instruction,
        )

        revised_eus = revised_generated.eus
        revised_traceability = revised_generated.traceability

        revised_checks = run_deterministic_checks(revised_eus)

        revised_traceability_checks = run_traceability_checks(
            analysis=analysis,
            eus=revised_eus,
            traceability=revised_traceability,
        )

        final_validation = self.agents.validate(
            requirement=requirement,
            candidate=revised_eus,
            checks=revised_checks,
            analysis=analysis,
            traceability=revised_traceability,
            traceability_checks=revised_traceability_checks,
            previous_draft=eus,
            previous_feedback=initial_validation,
        )

        return EUSRevisionArtifacts(
            requirement=requirement,
            model=self.llm.model,
            analysis=analysis,
            original_eus=eus,
            original_traceability=traceability,
            revision_instruction=revision_instruction,
            original_checks=original_checks,
            original_traceability_checks=traceability_checks,
            initial_validation=initial_validation,
            revised_eus=revised_eus,
            revised_traceability=revised_traceability,
            revised_checks=revised_checks,
            revised_traceability_checks=revised_traceability_checks,
            final_validation=final_validation,
            api_response_ids=self.llm.response_ids[response_start:],
        )

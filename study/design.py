from __future__ import annotations

import random
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


DEFAULT_SEED = 20260916
COUNTERBALANCE_BLOCK_SIZE = 16

FIRST_BLOCK_OFFSETS = (0, 1, 3)
SECOND_BLOCK_OFFSETS = (5, 6, 7)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StudyCondition(str, Enum):
    manual = "manual"
    eai_usg = "eai_usg"


class EthicalPrinciple(str, Enum):
    transparency = "Transparency"
    privacy = "Privacy"
    freedom_autonomy = "Freedom & Autonomy"
    justice_equity = "Justice & Equity"


class StudyRequirement(StrictModel):
    id: str
    principle: EthicalPrinciple


class StudyTask(StrictModel):
    task_number: int = Field(ge=1, le=6)
    requirement_id: str
    principle: EthicalPrinciple
    condition: StudyCondition


class ParticipantAssignment(StrictModel):
    participant_id: str
    participant_number: int = Field(ge=1)
    counterbalance_block: int = Field(ge=1)
    schedule_position: int = Field(ge=0, lt=COUNTERBALANCE_BLOCK_SIZE)
    condition_order: list[StudyCondition] = Field(min_length=2, max_length=2)
    tasks: list[StudyTask] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def validate_assignment(self) -> "ParticipantAssignment":
        if set(self.condition_order) != {StudyCondition.manual, StudyCondition.eai_usg}:
            raise ValueError("Condition order must contain Manual and EAI-USG exactly once.")

        requirement_ids = [task.requirement_id for task in self.tasks]

        if len(set(requirement_ids)) != 6:
            raise ValueError("A participant must receive six distinct requirements.")

        manual_count = sum(task.condition == StudyCondition.manual for task in self.tasks)
        eai_usg_count = sum(task.condition == StudyCondition.eai_usg for task in self.tasks)

        if manual_count != 3 or eai_usg_count != 3:
            raise ValueError("A participant must receive exactly three tasks per condition.")

        task_numbers = [task.task_number for task in self.tasks]

        if task_numbers != list(range(1, 7)):
            raise ValueError("Task numbers must be sequential from 1 to 6.")

        if any(task.condition != self.condition_order[0] for task in self.tasks[:3]):
            raise ValueError("The first three tasks must use the first assigned condition.")

        if any(task.condition != self.condition_order[1] for task in self.tasks[3:]):
            raise ValueError("The final three tasks must use the second assigned condition.")

        represented_principles = {task.principle for task in self.tasks}

        if represented_principles != set(EthicalPrinciple):
            raise ValueError("Each participant must receive tasks covering all four ethical principles.")

        return self


STUDY_REQUIREMENTS = (
    StudyRequirement(id="HUM-T01", principle=EthicalPrinciple.transparency),
    StudyRequirement(id="HUM-P01", principle=EthicalPrinciple.privacy),
    StudyRequirement(id="HUM-F01", principle=EthicalPrinciple.freedom_autonomy),
    StudyRequirement(id="HUM-J01", principle=EthicalPrinciple.justice_equity),
    StudyRequirement(id="HUM-T02", principle=EthicalPrinciple.transparency),
    StudyRequirement(id="HUM-P02", principle=EthicalPrinciple.privacy),
    StudyRequirement(id="HUM-F02", principle=EthicalPrinciple.freedom_autonomy),
    StudyRequirement(id="HUM-J02", principle=EthicalPrinciple.justice_equity),
    StudyRequirement(id="HUM-T03", principle=EthicalPrinciple.transparency),
    StudyRequirement(id="HUM-P03", principle=EthicalPrinciple.privacy),
    StudyRequirement(id="HUM-F03", principle=EthicalPrinciple.freedom_autonomy),
    StudyRequirement(id="HUM-J03", principle=EthicalPrinciple.justice_equity),
    StudyRequirement(id="HUM-T04", principle=EthicalPrinciple.transparency),
    StudyRequirement(id="HUM-P04", principle=EthicalPrinciple.privacy),
    StudyRequirement(id="HUM-F04", principle=EthicalPrinciple.freedom_autonomy),
    StudyRequirement(id="HUM-J04", principle=EthicalPrinciple.justice_equity),
)


def _get_schedule_position(participant_number: int) -> tuple[int, int]:
    zero_based = participant_number - 1
    block_index = zero_based // COUNTERBALANCE_BLOCK_SIZE
    local_position = zero_based % COUNTERBALANCE_BLOCK_SIZE

    block_shift = (block_index * 5) % COUNTERBALANCE_BLOCK_SIZE
    schedule_position = (local_position + block_shift) % COUNTERBALANCE_BLOCK_SIZE

    return block_index + 1, schedule_position


def _get_condition_order(schedule_position: int) -> tuple[StudyCondition, StudyCondition]:
    if schedule_position % 2 == 0:
        return StudyCondition.manual, StudyCondition.eai_usg

    return StudyCondition.eai_usg, StudyCondition.manual


def _get_requirement(offset: int, schedule_position: int) -> StudyRequirement:
    index = (schedule_position + offset) % len(STUDY_REQUIREMENTS)
    return STUDY_REQUIREMENTS[index]


def create_assignment(
    participant_number: int,
    seed: int = DEFAULT_SEED,
) -> ParticipantAssignment:
    if participant_number < 1:
        raise ValueError("Participant number must be at least 1.")

    counterbalance_block, schedule_position = _get_schedule_position(participant_number)
    first_condition, second_condition = _get_condition_order(schedule_position)

    rng = random.Random(seed + participant_number * 1009)

    first_offsets = list(FIRST_BLOCK_OFFSETS)
    second_offsets = list(SECOND_BLOCK_OFFSETS)

    rng.shuffle(first_offsets)
    rng.shuffle(second_offsets)

    tasks: list[StudyTask] = []

    for offset in first_offsets:
        requirement = _get_requirement(offset, schedule_position)

        tasks.append(
            StudyTask(
                task_number=len(tasks) + 1,
                requirement_id=requirement.id,
                principle=requirement.principle,
                condition=first_condition,
            )
        )

    for offset in second_offsets:
        requirement = _get_requirement(offset, schedule_position)

        tasks.append(
            StudyTask(
                task_number=len(tasks) + 1,
                requirement_id=requirement.id,
                principle=requirement.principle,
                condition=second_condition,
            )
        )

    return ParticipantAssignment(
        participant_id=f"P{participant_number:03d}",
        participant_number=participant_number,
        counterbalance_block=counterbalance_block,
        schedule_position=schedule_position,
        condition_order=[first_condition, second_condition],
        tasks=tasks,
    )


def create_schedule(
    participant_count: int,
    seed: int = DEFAULT_SEED,
) -> list[ParticipantAssignment]:
    if participant_count < 1:
        raise ValueError("Participant count must be at least 1.")

    return [
        create_assignment(participant_number, seed=seed)
        for participant_number in range(1, participant_count + 1)
    ]


def summarize_schedule(assignments: list[ParticipantAssignment]) -> dict:
    requirement_counts = {
        requirement.id: {
            StudyCondition.manual.value: 0,
            StudyCondition.eai_usg.value: 0,
        }
        for requirement in STUDY_REQUIREMENTS
    }

    principle_counts = {
        principle.value: {
            StudyCondition.manual.value: 0,
            StudyCondition.eai_usg.value: 0,
        }
        for principle in EthicalPrinciple
    }

    condition_order_counts = {
        "manual_first": 0,
        "eai_usg_first": 0,
    }

    for assignment in assignments:
        if assignment.condition_order[0] == StudyCondition.manual:
            condition_order_counts["manual_first"] += 1
        else:
            condition_order_counts["eai_usg_first"] += 1

        for task in assignment.tasks:
            requirement_counts[task.requirement_id][task.condition.value] += 1
            principle_counts[task.principle.value][task.condition.value] += 1

    return {
        "participants": len(assignments),
        "condition_order": condition_order_counts,
        "requirements": requirement_counts,
        "principles": principle_counts,
    }

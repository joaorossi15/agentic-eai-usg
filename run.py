from __future__ import annotations

import argparse

from eai_usg.io import save_run
from eai_usg.pipeline import EAIUSGPipeline, WorkflowConfig
from eai_usg.schemas import EthicalRequirement


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True)
    parser.add_argument("--requirement", required=True)
    parser.add_argument(
        "--config",
        choices=[config.value for config in WorkflowConfig],
        default=WorkflowConfig.FULL.value,
    )
    parser.add_argument("--model", default=None)
    parser.add_argument("--threshold", type=int, default=None)
    args = parser.parse_args()

    pipeline = EAIUSGPipeline(
        model=args.model,
        quality_threshold=args.threshold,
    )

    requirement = EthicalRequirement(
        id=args.id,
        text=args.requirement,
    )

    result = pipeline.run(
        requirement=requirement,
        config=WorkflowConfig(args.config),
    )

    path = save_run(result)

    print(result.final_eus.model_dump_json(indent=2))

    if result.final_traceability is not None:
        print("\nTraceability:")
        print(result.final_traceability.model_dump_json(indent=2))

    print(f"\nStatus: {result.status.value}")

    if result.review_reason is not None:
        print(f"Review reason: {result.review_reason.value}")

    print(f"Saved run: {path}")


if __name__ == "__main__":
    main()

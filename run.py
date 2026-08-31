from __future__ import annotations

import argparse

from eai_usg.io import save_run
from eai_usg.pipeline import EAIUSGPipeline, WorkflowConfig
from eai_usg.schemas import EthicalRequirement


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True)
    parser.add_argument("--requirement", required=True)
    parser.add_argument("--config", choices=[c.value for c in WorkflowConfig], default=WorkflowConfig.FULL.value)
    parser.add_argument("--model", default=None)
    parser.add_argument("--threshold", type=int, default=None)
    args = parser.parse_args()

    pipeline = EAIUSGPipeline(model=args.model, quality_threshold=args.threshold)
    result = pipeline.run(
        EthicalRequirement(id=args.id, text=args.requirement),
        WorkflowConfig(args.config),
    )
    path = save_run(result)
    print(result.final_eus.model_dump_json(indent=2))
    print(f"\nSaved run: {path}")


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse

from eai_usg.io import save_backend_run
from eai_usg.pipeline import EAIUSGPipeline
from eai_usg.schemas import EthicalRequirement


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True)
    parser.add_argument("--requirement", required=True)
    parser.add_argument(
        "--backend",
        required=True,
        choices=["openai", "anthropic", "google"],
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--repetition", type=int, required=True)
    parser.add_argument("--output-dir", default="outputs/backend_runs")
    args = parser.parse_args()

    pipeline = EAIUSGPipeline(
        backend=args.backend,
        model=args.model,
    )

    requirement = EthicalRequirement(
        id=args.id,
        text=args.requirement,
    )

    result = pipeline.run(
        requirement=requirement,
        repetition=args.repetition,
    )

    path = save_backend_run(
        result,
        output_dir=args.output_dir,
    )

    print(result.eus.model_dump_json(indent=2))

    print("\nDeterministic checks:")
    print(result.checks.model_dump_json(indent=2))

    print(f"\nBackend: {result.backend}")
    print(f"Model: {result.model}")
    print(f"Repetition: {result.repetition}")
    print(f"Saved run: {path}")


if __name__ == "__main__":
    main()

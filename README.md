# Agentic EAI-USG research prototype

A minimal bounded agentic workflow implemented in plain Python.

## Pipeline

Requirement -> Analysis -> Generation -> Critique -> Revision -> Validation
-> optional one targeted revision -> Final EUS

## Supported configurations

- `full`
- `no_analysis`
- `no_critique_revision`
- `no_validation`
- `single_pass`

The `single_pass` baseline uses the same underlying model as the full workflow.
Additional frontier-provider baselines can be added later as separate adapters.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Put your OpenAI API key in `.env`.

## Run

```bash
python run.py \
  --config full \
  --id DEV-001 \
  --requirement "Users must be informed when they are interacting with an AI system."
```

Each run is saved under `outputs/runs/` as JSON, including intermediate artifacts and API response IDs.

## Research rule

Use only the designated development requirements while tuning prompts, schemas,
thresholds, or orchestration. Keep ablation and Human-AI requirements untouched.

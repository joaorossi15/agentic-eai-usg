from __future__ import annotations

import json
import os
from typing import Type, TypeVar

from anthropic import Anthropic
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

T = TypeVar("T", bound=BaseModel)


class StructuredLLM:
    def __init__(
        self,
        backend: str | None = None,
        model: str | None = None,
    ):
        self.backend = backend or os.getenv(
            "EAI_BACKEND",
            "anthropic",
        )

        if self.backend != "anthropic":
            raise ValueError(
                "The Human-AI study configuration is frozen to "
                "the Anthropic backend."
            )

        self.model = model or os.getenv(
            "EAI_MODEL",
            "claude-fable-5-1",
        )

        self.client = Anthropic()
        self.response_ids: list[str] = []

    def generate(
        self,
        *,
        agent_name: str,
        instructions: str,
        user_payload: dict,
        output_model: Type[T],
    ) -> T:
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=int(
                os.getenv(
                    "EAI_MAX_OUTPUT_TOKENS",
                    "4096",
                )
            ),
            system=instructions,
            messages=[
                {
                    "role": "user",
                    "content": json.dumps(
                        user_payload,
                        ensure_ascii=False,
                        indent=2,
                    ),
                }
            ],
            output_format=output_model,
        )

        if getattr(response, "id", None):
            self.response_ids.append(
                response.id
            )

        if response.parsed_output is None:
            raise ValueError(
                f"No structured output returned for {agent_name}."
            )

        return response.parsed_output

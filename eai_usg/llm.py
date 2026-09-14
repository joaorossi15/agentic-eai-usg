from __future__ import annotations

import json
import os
from typing import Type, TypeVar

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

T = TypeVar("T", bound=BaseModel)


class StructuredLLM:
    def __init__(
        self,
        backend: str,
        model: str,
    ):
        self.backend = backend.lower()
        self.model = model
        self.response_ids: list[str] = []

        if self.backend == "openai":
            from openai import OpenAI

            self.client = OpenAI()

        elif self.backend == "anthropic":
            from anthropic import Anthropic

            self.client = Anthropic()

        elif self.backend == "google":
            from google import genai

            self.client = genai.Client()

        else:
            raise ValueError(
                f"Unsupported backend: {backend}. "
                "Expected one of: openai, anthropic, google."
            )

    def generate(
        self,
        *,
        agent_name: str,
        instructions: str,
        user_payload: dict,
        output_model: Type[T],
    ) -> T:
        if self.backend == "openai":
            return self._generate_openai(
                agent_name=agent_name,
                instructions=instructions,
                user_payload=user_payload,
                output_model=output_model,
            )

        if self.backend == "anthropic":
            return self._generate_anthropic(
                instructions=instructions,
                user_payload=user_payload,
                output_model=output_model,
            )

        return self._generate_google(
            instructions=instructions,
            user_payload=user_payload,
            output_model=output_model,
        )

    def _generate_openai(
        self,
        *,
        agent_name: str,
        instructions: str,
        user_payload: dict,
        output_model: Type[T],
    ) -> T:
        response = self.client.responses.create(
            model=self.model,
            instructions=instructions,
            input=json.dumps(user_payload, ensure_ascii=False, indent=2),
            text={
                "format": {
                    "type": "json_schema",
                    "name": agent_name,
                    "description": f"Structured output for EAI-USG {agent_name}.",
                    "schema": output_model.model_json_schema(),
                    "strict": True,
                }
            },
        )

        if getattr(response, "id", None):
            self.response_ids.append(response.id)

        return output_model.model_validate_json(response.output_text)

    def _generate_anthropic(
        self,
        *,
        instructions: str,
        user_payload: dict,
        output_model: Type[T],
    ) -> T:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=int(os.getenv("EAI_MAX_OUTPUT_TOKENS", "2048")),
            system=instructions,
            messages=[
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False, indent=2),
                }
            ],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": output_model.model_json_schema(),
                }
            },
        )

        if getattr(response, "id", None):
            self.response_ids.append(response.id)

        output_text = next(
            block.text
            for block in response.content
            if block.type == "text"
        )

        return output_model.model_validate_json(output_text)

    def _generate_google(
        self,
        *,
        instructions: str,
        user_payload: dict,
        output_model: Type[T],
    ) -> T:
        interaction = self.client.interactions.create(
            model=self.model,
            system_instruction=instructions,
            input=json.dumps(user_payload, ensure_ascii=False, indent=2),
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": output_model.model_json_schema(),
            },
        )

        if getattr(interaction, "id", None):
            self.response_ids.append(interaction.id)

        return output_model.model_validate_json(interaction.output_text)

from __future__ import annotations

import json
import os
from typing import Type, TypeVar

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

load_dotenv()
T = TypeVar("T", bound=BaseModel)


class StructuredLLM:
    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("EAI_MODEL", "gpt-5.6-terra")
        self.client = OpenAI()
        self.response_ids: list[str] = []

    def generate(self, *, agent_name: str, instructions: str, user_payload: dict, output_model: Type[T]) -> T:
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

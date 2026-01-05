from __future__ import annotations

import json
from dataclasses import dataclass

from marketplace.config import Settings, settings
from marketplace.parsing import visible_text
from marketplace.schemas import ProductExtraction

PROMPT_VERSION = "v1"


@dataclass
class LLMResult:
    extraction: ProductExtraction
    raw_response: dict
    model: str
    prompt_version: str = PROMPT_VERSION


class ProductExtractor:
    def __init__(self, config: Settings = settings):
        if not config.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for --with-llm")
        if not config.openai_model:
            raise RuntimeError("OPENAI_MODEL is required for --with-llm")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install the 'openai' package to use --with-llm") from exc
        self.config = config
        self.client = OpenAI(
            api_key=config.openai_api_key,
            base_url=config.normalized_openai_base_url,
        )

    def extract(self, source: str, url: str, html: str) -> LLMResult:
        schema = ProductExtraction.model_json_schema()
        prompt = (
            "Extract product metadata from the marketplace page text below. Return only valid JSON "
            "matching this schema. Use null when a value is absent. Do not invent values.\n\n"
            f"Schema:\n{json.dumps(schema)}\n\nSource: {source}\nURL: {url}\n"
            f"Page text:\n{visible_text(html)}"
        )
        response = self.client.chat.completions.create(
            model=self.config.openai_model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are a careful product data extraction service."},
                {"role": "user", "content": prompt},
            ],
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        extraction = ProductExtraction.model_validate(parsed)
        return LLMResult(
            extraction=extraction,
            raw_response={"content": content, "model": response.model},
            model=response.model or self.config.openai_model,
        )

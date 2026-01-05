from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///marketplace.db")
    raw_html_dir: str = os.getenv("RAW_HTML_DIR", "data/raw")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY") or None
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://llm.arc.vt.edu/")
    openai_model: str | None = os.getenv("OPENAI_MODEL") or None

    @property
    def normalized_openai_base_url(self) -> str:
        """Return an SDK-compatible base URL while accepting a host-only env value."""
        parsed = urlparse(self.openai_base_url)
        if parsed.hostname == "llm.arc.vt.edu":
            return "https://llm-api.arc.vt.edu/api/v1"
        if parsed.scheme and parsed.netloc and parsed.path in ("", "/"):
            return self.openai_base_url.rstrip("/") + "/v1"
        return self.openai_base_url.rstrip("/")


settings = Settings()

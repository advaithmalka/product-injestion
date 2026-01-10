from __future__ import annotations

import json
import logging
import time
from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

logger = logging.getLogger("marketplace")

pages_total = Counter("marketplace_pages_total", "Pages processed", ["source", "status"])
page_retries_total = Counter(
    "marketplace_page_retries_total", "Page collection retries", ["source"]
)
llm_requests_total = Counter(
    "marketplace_llm_requests_total", "LLM extraction attempts", ["status"]
)
page_duration_seconds = Histogram(
    "marketplace_page_duration_seconds", "Page processing duration", ["source"]
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("run_id", "source", "url", "page_key", "status", "error"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    if not logging.getLogger().handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logging.basicConfig(level=level, handlers=[handler])


def metrics_payload() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST


class Timer:
    def __init__(self, histogram: Histogram, **labels: str):
        self.histogram = histogram
        self.labels = labels
        self.started = 0.0

    def __enter__(self):
        self.started = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.histogram.labels(**self.labels).observe(time.perf_counter() - self.started)

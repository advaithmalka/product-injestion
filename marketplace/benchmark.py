from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from marketplace.collectors import FixturePageCollector
from marketplace.parsing import parse_html
from marketplace.pipeline import load_manifest


def run_parser_benchmark(manifest_path: str | Path, events: int) -> dict[str, Any]:
    if events < 1:
        raise ValueError("events must be positive")
    items = load_manifest(manifest_path)
    if not items:
        raise ValueError("manifest must contain at least one page")
    collector = FixturePageCollector()
    succeeded = 0
    failed = 0
    started = time.perf_counter()
    for index in range(events):
        item = items[index % len(items)]
        try:
            html = collector.collect(item.url, item.html_path)
            parse_html(item.source, html, item.url)
            succeeded += 1
        except Exception:  # noqa: BLE001 - benchmark reports parser failures by event
            failed += 1
    duration = time.perf_counter() - started
    return {
        "stage": "fixture-html-parser-normalizer",
        "events": events,
        "succeeded": succeeded,
        "failed": failed,
        "duration_seconds": round(duration, 4),
        "events_per_second": round(succeeded / duration, 2) if duration else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark fixture HTML parsing and normalization")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--events", type=int, default=150_000)
    args = parser.parse_args()
    print(json.dumps(run_parser_benchmark(args.manifest, args.events), indent=2))

from __future__ import annotations

import argparse
import json

from marketplace.collectors import FixturePageCollector, SeleniumPageCollector
from marketplace.config import settings
from marketplace.llm import ProductExtractor
from marketplace.pipeline import run_ingestion


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest marketplace product pages")
    parser.add_argument("--manifest", required=True, help="Path to a JSON or CSV Page Manifest")
    parser.add_argument(
        "--with-llm", action="store_true", help="Use the configured compatible LLM endpoint"
    )
    parser.add_argument(
        "--live", action="store_true", help="Allow Selenium to fetch URLs without html_path"
    )
    parser.add_argument(
        "--max-retries", type=int, default=2, help="Retries for transient page collection failures"
    )
    parser.add_argument(
        "--run-id", help="Stable run ID for idempotent re-execution of a completed run"
    )
    args = parser.parse_args()

    collector = SeleniumPageCollector() if args.live else FixturePageCollector()
    extractor = ProductExtractor(settings) if args.with_llm else None
    result = run_ingestion(
        args.manifest, collector, settings, extractor, args.max_retries, args.run_id
    )
    print(json.dumps(result, indent=2))

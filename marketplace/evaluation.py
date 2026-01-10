from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Optional

from marketplace.collectors import FixturePageCollector
from marketplace.config import Settings, settings
from marketplace.llm import ProductExtractor
from marketplace.parsing import parse_html
from marketplace.pipeline import _merge_extractions


def _same(expected: Any, actual: Any) -> bool:
    if expected is None:
        return actual is None
    if isinstance(expected, float) and isinstance(actual, (float, int)):
        return abs(expected - actual) < 0.01
    return expected == actual


def evaluate_gold_set(
    gold_path: str | Path,
    config: Settings = settings,
    extractor: Optional[ProductExtractor] = None,
) -> dict[str, Any]:
    gold_file = Path(gold_path)
    entries = json.loads(gold_file.read_text(encoding="utf-8"))
    collector = FixturePageCollector()
    totals: dict[str, int] = {}
    correct: dict[str, int] = {}
    pages = 0
    for entry in entries:
        html_path = Path(entry["html_path"])
        if not html_path.is_absolute():
            html_path = (gold_file.parent / html_path).resolve()
        html = collector.collect(entry["url"], str(html_path))
        baseline = parse_html(entry["source"], html, entry["url"])
        if extractor:
            extraction = _merge_extractions(
                baseline, extractor.extract(entry["source"], entry["url"], html)
            )
        else:
            extraction = baseline
        for field, expected in entry["expected"].items():
            totals[field] = totals.get(field, 0) + 1
            if _same(expected, getattr(extraction, field)):
                correct[field] = correct.get(field, 0) + 1
        pages += 1
    field_accuracy = {
        field: round(correct.get(field, 0) / total, 4) for field, total in totals.items()
    }
    overall = sum(correct.values()) / sum(totals.values()) if totals else 0.0
    return {"pages": pages, "field_accuracy": field_accuracy, "overall_accuracy": round(overall, 4)}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate marketplace extraction against a gold set"
    )
    parser.add_argument("--gold", required=True, help="Path to the labeled JSON gold set")
    parser.add_argument("--with-llm", action="store_true")
    args = parser.parse_args()
    extractor = ProductExtractor(settings) if args.with_llm else None
    print(json.dumps(evaluate_gold_set(args.gold, settings, extractor), indent=2))

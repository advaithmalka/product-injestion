from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from marketplace.collectors import PageCollector
from marketplace.config import Settings, settings
from marketplace.db import initialize_database, session_scope
from marketplace.llm import ProductExtractor
from marketplace.models import ExtractionRun, Observation, Product, SourceListing
from marketplace.normalization import canonical_key, normalize_text
from marketplace.parsing import parse_html
from marketplace.schemas import ManifestItem, ProductExtraction


def load_manifest(path: str | Path) -> list[ManifestItem]:
    path = Path(path)
    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path)
        values = frame.to_dict(orient="records")
    else:
        values = json.loads(path.read_text(encoding="utf-8"))
    items = [ManifestItem.model_validate(value) for value in values]
    for item in items:
        if item.html_path and not Path(item.html_path).is_absolute():
            object.__setattr__(item, "html_path", str((path.parent / item.html_path).resolve()))
    return items


def _source_item_id(item: ManifestItem) -> str:
    return item.source_item_id or hashlib.sha256(item.url.encode()).hexdigest()[:20]


def _find_or_create_product(session: Session, extraction: ProductExtraction) -> Product:
    key = canonical_key(extraction)
    product = session.scalar(select(Product).where(Product.canonical_key == key))
    if product:
        product.title = extraction.title or product.title
        product.brand = extraction.brand or product.brand
        product.model = extraction.model or product.model
        product.category = extraction.category or product.category
        product.description = extraction.description or product.description
        product.attributes = {**(product.attributes or {}), **(extraction.attributes or {})}
        return product
    product = Product(
        canonical_key=key,
        title=extraction.title,
        brand=extraction.brand,
        model=extraction.model,
        category=extraction.category,
        description=extraction.description,
        attributes=extraction.attributes,
    )
    session.add(product)
    session.flush()
    return product


def _save_raw_html(raw_dir: str, run_id: str, item: ManifestItem, html: str) -> str:
    destination = Path(raw_dir) / run_id
    destination.mkdir(parents=True, exist_ok=True)
    filename = f"{normalize_text(item.source)}-{hashlib.sha256(item.url.encode()).hexdigest()[:16]}.html"
    path = destination / filename
    path.write_text(html, encoding="utf-8")
    return str(path)


def _collect_with_retry(collector: PageCollector, item: ManifestItem, max_retries: int) -> str:
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            return collector.collect(item.url, item.html_path)
        except Exception as exc:
            last_error = exc
            if attempt == max_retries:
                break
            time.sleep(0.25 * (2**attempt))
    raise last_error  # type: ignore[misc]


def run_ingestion(
    manifest_path: str | Path,
    collector: PageCollector,
    config: Settings = settings,
    extractor: ProductExtractor | None = None,
    max_retries: int = 2,
) -> dict:
    initialize_database(config.database_url)
    items = load_manifest(manifest_path)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    session: Session = session_scope(config.database_url)
    summary = {"run_id": run_id, "total": len(items), "succeeded": 0, "failed": 0, "errors": []}
    try:
        for item in items:
            extraction_run = ExtractionRun(status="started", model=config.openai_model if extractor else None)
            session.add(extraction_run)
            try:
                html = _collect_with_retry(collector, item, max_retries)
                raw_path = _save_raw_html(config.raw_html_dir, run_id, item, html)
                baseline = parse_html(item.source, html, item.url)
                llm_result = extractor.extract(item.source, item.url, html) if extractor else None
                if llm_result:
                    baseline_data = baseline.model_dump()
                    llm_data = llm_result.extraction.model_dump()
                    extraction = ProductExtraction.model_validate(
                        {
                            **baseline_data,
                            **{
                                key: value
                                for key, value in llm_data.items()
                                if value is not None and value != {}
                            },
                        }
                    )
                else:
                    extraction = baseline
                product = _find_or_create_product(session, extraction)
                listing = session.scalar(
                    select(SourceListing).where(
                        SourceListing.source == item.source,
                        SourceListing.source_item_id == _source_item_id(item),
                    )
                )
                if not listing:
                    listing = SourceListing(
                        source=item.source,
                        source_item_id=_source_item_id(item),
                        url=item.url,
                        product_id=product.id,
                        title=extraction.title,
                        raw_html_path=raw_path,
                        source_metadata={"manifest": str(manifest_path)},
                    )
                    session.add(listing)
                    session.flush()
                else:
                    listing.product_id = product.id
                    listing.title = extraction.title
                    listing.raw_html_path = raw_path
                observation = Observation(
                    listing_id=listing.id,
                    price=extraction.price,
                    currency=extraction.currency,
                    availability=extraction.availability,
                    condition=extraction.condition,
                    review_count=extraction.review_count,
                    rating=extraction.rating,
                    attributes=extraction.attributes,
                )
                session.add(observation)
                extraction_run.listing_id = listing.id
                extraction_run.status = "succeeded"
                extraction_run.raw_response = llm_result.raw_response if llm_result else extraction.model_dump()
                extraction_run.model = llm_result.model if llm_result else "baseline-parser"
                summary["succeeded"] += 1
            except Exception as exc:  # one page must not poison the batch
                extraction_run.status = "failed"
                extraction_run.error = str(exc)
                summary["failed"] += 1
                summary["errors"].append({"url": item.url, "error": str(exc)})
        session.commit()
    finally:
        session.close()
    return summary

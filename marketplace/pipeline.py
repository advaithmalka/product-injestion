from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from marketplace.collectors import PageCollector
from marketplace.config import Settings, settings
from marketplace.db import initialize_database, session_scope
from marketplace.llm import LLMResult, ProductExtractor
from marketplace.models import (
    DeadLetter,
    ExtractionRun,
    IngestionRun,
    Observation,
    PageAttempt,
    Product,
    ProductMatchCandidate,
    SourceListing,
)
from marketplace.normalization import canonical_key, normalize_text
from marketplace.observability import (
    Timer,
    llm_requests_total,
    logger,
    page_duration_seconds,
    page_retries_total,
    pages_total,
)
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


def _manifest_hash(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _source_item_id(item: ManifestItem) -> str:
    return item.source_item_id or hashlib.sha256(item.url.encode()).hexdigest()[:20]


def _page_key(item: ManifestItem) -> str:
    url_key = hashlib.sha256(item.url.encode()).hexdigest()[:16]
    return f"{normalize_text(item.source)}:{_source_item_id(item)}:{url_key}"


def _validation_errors(error: Exception) -> list[str]:
    if isinstance(error, ValidationError):
        return [f"{'.'.join(str(part) for part in detail['loc'])}: {detail['msg']}" for detail in error.errors()]
    return [str(error)]


def _find_or_create_product(
    session: Session, extraction: ProductExtraction
) -> tuple[Product, list[tuple[Product, float]]]:
    """Resolve strong identifiers, then return reviewable fuzzy candidates for new products."""
    product: Optional[Product] = None
    if extraction.gtin:
        product = session.scalar(select(Product).where(Product.gtin == extraction.gtin))
    if not product and extraction.brand and extraction.manufacturer_part_number:
        product = session.scalar(
            select(Product).where(
                Product.brand == extraction.brand,
                Product.manufacturer_part_number == extraction.manufacturer_part_number,
            )
        )
    key = canonical_key(extraction)
    if not product:
        product = session.scalar(select(Product).where(Product.canonical_key == key))

    if product:
        product.title = extraction.title or product.title
        product.brand = extraction.brand or product.brand
        product.model = extraction.model or product.model
        product.gtin = extraction.gtin or product.gtin
        product.manufacturer_part_number = extraction.manufacturer_part_number or product.manufacturer_part_number
        product.category = extraction.category or product.category
        product.description = extraction.description or product.description
        product.attributes = {**(product.attributes or {}), **(extraction.attributes or {})}
        return product, []

    candidates: list[tuple[Product, float]] = []
    normalized_title = normalize_text(extraction.title)
    for candidate in session.scalars(select(Product)).all():
        score = SequenceMatcher(None, normalized_title, normalize_text(candidate.title)).ratio()
        if score >= 0.75:
            candidates.append((candidate, round(score, 4)))
    product = Product(
        canonical_key=key,
        title=extraction.title,
        brand=extraction.brand,
        model=extraction.model,
        gtin=extraction.gtin,
        manufacturer_part_number=extraction.manufacturer_part_number,
        category=extraction.category,
        description=extraction.description,
        attributes=extraction.attributes,
    )
    session.add(product)
    session.flush()
    return product, candidates


def _save_raw_html(raw_dir: str, run_id: str, item: ManifestItem, html: str) -> str:
    destination = Path(raw_dir) / run_id
    destination.mkdir(parents=True, exist_ok=True)
    filename = f"{normalize_text(item.source)}-{hashlib.sha256(item.url.encode()).hexdigest()[:16]}.html"
    path = destination / filename
    path.write_text(html, encoding="utf-8")
    return str(path)


def _collect_with_retry(
    session: Session,
    ingestion_run: IngestionRun,
    collector: PageCollector,
    item: ManifestItem,
    max_retries: int,
    run_id: str,
) -> tuple[Optional[str], Optional[PageAttempt], Optional[str]]:
    last_attempt: Optional[PageAttempt] = None
    last_error: Optional[str] = None
    for attempt_number in range(max_retries + 1):
        attempt = PageAttempt(
            ingestion_run_id=ingestion_run.id,
            page_key=_page_key(item),
            source=item.source,
            source_item_id=_source_item_id(item),
            url=item.url,
            attempt_number=attempt_number,
            status="started",
        )
        session.add(attempt)
        session.flush()
        last_attempt = attempt
        try:
            html = collector.collect(item.url, item.html_path)
            attempt.status = "succeeded"
            attempt.finished_at = datetime.now(timezone.utc)
            logger.info(
                "page collected",
                extra={"run_id": run_id, "source": item.source, "url": item.url, "page_key": _page_key(item)},
            )
            return html, attempt, None
        except Exception as exc:  # noqa: BLE001 - batch boundary records arbitrary adapter failures
            last_error = str(exc)
            attempt.status = "failed"
            attempt.error = last_error
            attempt.finished_at = datetime.now(timezone.utc)
            if attempt_number < max_retries:
                page_retries_total.labels(source=item.source).inc()
                time.sleep(0.25 * (2**attempt_number))
    return None, last_attempt, last_error


def _extract_with_retry(
    extractor: ProductExtractor,
    item: ManifestItem,
    html: str,
    max_retries: int,
) -> tuple[Optional[LLMResult], Optional[str]]:
    last_error: Optional[str] = None
    for attempt_number in range(max_retries + 1):
        try:
            result = extractor.extract(item.source, item.url, html)
            llm_requests_total.labels(status="succeeded").inc()
            return result, None
        except Exception as exc:  # noqa: BLE001 - compatible providers expose different error classes
            last_error = str(exc)
            llm_requests_total.labels(status="failed").inc()
            if attempt_number < max_retries:
                time.sleep(0.5 * (2**attempt_number))
    return None, last_error


def _merge_extractions(baseline: ProductExtraction, llm_result: LLMResult) -> ProductExtraction:
    baseline_data = baseline.model_dump()
    llm_data = llm_result.extraction.model_dump()
    merged = {
        **baseline_data,
        **{
            key: value
            for key, value in llm_data.items()
            if value is not None and value != {}
        },
    }
    merged["evidence"] = {**baseline.evidence, **llm_result.extraction.evidence}
    merged["confidence"] = {**baseline.confidence, **llm_result.extraction.confidence}
    return ProductExtraction.model_validate(merged)


def _record_candidates(session: Session, listing: SourceListing, candidates: list[tuple[Product, float]]) -> None:
    for product, score in candidates:
        session.add(
            ProductMatchCandidate(
                source_listing_id=listing.id,
                candidate_product_id=product.id,
                score=score,
                method="normalized-title-fuzzy",
                status="pending",
            )
        )


def _summary(run: IngestionRun) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "total": run.total_pages,
        "succeeded": run.succeeded_pages,
        "failed": run.failed_pages,
        "fallbacks": run.fallback_pages,
        "dead_letters": len(run.dead_letters),
        "status": run.status,
        "errors": [{"url": dead.url, "error": dead.error} for dead in run.dead_letters],
    }


def run_ingestion(
    manifest_path: str | Path,
    collector: PageCollector,
    config: Settings = settings,
    extractor: ProductExtractor | None = None,
    max_retries: int = 2,
    run_id: str | None = None,
) -> dict:
    initialize_database(config.database_url)
    items = load_manifest(manifest_path)
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    manifest_hash = _manifest_hash(manifest_path)
    session: Session = session_scope(config.database_url)
    try:
        existing = session.scalar(select(IngestionRun).where(IngestionRun.run_id == run_id))
        if existing:
            return _summary(existing)
        ingestion_run = IngestionRun(
            run_id=run_id,
            manifest_path=str(manifest_path),
            manifest_hash=manifest_hash,
            status="running",
            total_pages=len(items),
        )
        session.add(ingestion_run)
        session.flush()
        session.commit()

        for item in items:
            with Timer(page_duration_seconds, source=item.source):
                html, page_attempt, collection_error = _collect_with_retry(
                    session, ingestion_run, collector, item, max_retries, run_id
                )
                if collection_error:
                    session.add(
                        DeadLetter(
                            ingestion_run_id=ingestion_run.id,
                            page_attempt_id=page_attempt.id if page_attempt else None,
                            page_key=_page_key(item),
                            source=item.source,
                            source_item_id=_source_item_id(item),
                            url=item.url,
                            payload={"manifest_path": str(manifest_path)},
                            error=collection_error,
                        )
                    )
                    ingestion_run.failed_pages += 1
                    pages_total.labels(source=item.source, status="failed").inc()
                    logger.error(
                        "page moved to dead letter",
                        extra={"run_id": run_id, "source": item.source, "url": item.url, "error": collection_error},
                    )
                    session.commit()
                    continue

                assert html is not None and page_attempt is not None
                raw_path = _save_raw_html(config.raw_html_dir, run_id, item, html)
                page_attempt.raw_html_path = raw_path
                baseline = parse_html(item.source, html, item.url)
                llm_result: Optional[LLMResult] = None
                fallback_reason: Optional[str] = None
                if extractor:
                    llm_result, fallback_reason = _extract_with_retry(extractor, item, html, max_retries)
                extraction = _merge_extractions(baseline, llm_result) if llm_result else baseline
                extraction_run = ExtractionRun(
                    status="succeeded" if llm_result or not extractor else "fallback",
                    model=llm_result.model if llm_result else (config.openai_model if extractor else "baseline-parser"),
                    prompt_version=llm_result.prompt_version if llm_result else "baseline",
                    raw_response=llm_result.raw_response if llm_result else extraction.model_dump(),
                    validation_errors=_validation_errors(Exception(fallback_reason)) if fallback_reason else [],
                    field_provenance=extraction.evidence,
                    field_confidence=extraction.confidence,
                    fallback_reason=fallback_reason,
                    ingestion_run_id=ingestion_run.id,
                    page_attempt_id=page_attempt.id,
                )
                session.add(extraction_run)
                product, candidates = _find_or_create_product(session, extraction)
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
                        source_metadata={"manifest": str(manifest_path), "manifest_hash": manifest_hash},
                    )
                    session.add(listing)
                    session.flush()
                else:
                    listing.product_id = product.id
                    listing.title = extraction.title
                    listing.raw_html_path = raw_path
                _record_candidates(session, listing, candidates)
                session.add(
                    Observation(
                        listing_id=listing.id,
                        price=extraction.price,
                        currency=extraction.currency,
                        availability=extraction.availability,
                        condition=extraction.condition,
                        review_count=extraction.review_count,
                        rating=extraction.rating,
                        attributes={
                            **(extraction.attributes or {}),
                            "evidence": extraction.evidence,
                            "confidence": extraction.confidence,
                        },
                    )
                )
                extraction_run.listing_id = listing.id
                ingestion_run.succeeded_pages += 1
                if fallback_reason:
                    ingestion_run.fallback_pages += 1
                pages_total.labels(source=item.source, status="succeeded").inc()
                session.commit()

        ingestion_run.status = "completed_with_errors" if ingestion_run.failed_pages else "completed"
        ingestion_run.finished_at = datetime.now(timezone.utc)
        ingestion_run.summary = _summary(ingestion_run)
        session.commit()
        return _summary(ingestion_run)
    finally:
        session.close()

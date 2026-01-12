from __future__ import annotations

from typing import Any

from flask import Flask, jsonify, request
from sqlalchemy import select, text
from werkzeug.exceptions import HTTPException

from marketplace.config import settings
from marketplace.db import initialize_database, session_scope
from marketplace.models import (
    DeadLetter,
    ExtractionRun,
    IngestionRun,
    Product,
    ProductMatchCandidate,
)
from marketplace.observability import configure_logging, metrics_payload
from marketplace.trends import trend_signals


def _pagination() -> tuple[int, int]:
    try:
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))
    except ValueError as exc:
        raise ValueError("limit and offset must be integers") from exc
    if limit < 1 or offset < 0:
        raise ValueError("limit must be positive and offset cannot be negative")
    return min(limit, 100), offset


def _product_json(product: Product) -> dict[str, Any]:
    return {
        "id": product.id,
        "canonical_key": product.canonical_key,
        "title": product.title,
        "brand": product.brand,
        "model": product.model,
        "gtin": product.gtin,
        "manufacturer_part_number": product.manufacturer_part_number,
        "category": product.category,
        "description": product.description,
        "attributes": product.attributes,
        "listings": [
            {
                "id": listing.id,
                "source": listing.source,
                "source_item_id": listing.source_item_id,
                "url": listing.url,
                "title": listing.title,
                "raw_html_path": listing.raw_html_path,
                "observations": [
                    {
                        "observed_at": observation.observed_at.isoformat(),
                        "price": observation.price,
                        "currency": observation.currency,
                        "availability": observation.availability,
                        "condition": observation.condition,
                        "review_count": observation.review_count,
                        "rating": observation.rating,
                        "attributes": observation.attributes,
                    }
                    for observation in listing.observations
                ],
            }
            for listing in product.listings
        ],
    }


def create_app(database_url: str | None = None) -> Flask:
    configure_logging()
    app = Flask(__name__)
    db_url = database_url or settings.database_url
    initialize_database(db_url, create_schema=settings.auto_create_schema)

    @app.errorhandler(ValueError)
    def bad_request(error: ValueError):
        return jsonify({"error": str(error)}), 400

    @app.errorhandler(HTTPException)
    def http_error(error: HTTPException):
        return jsonify({"error": error.description}), error.code

    @app.errorhandler(Exception)
    def unexpected_error(error: Exception):
        app.logger.exception("request failed")
        return jsonify({"error": "internal server error"}), 500

    @app.get("/health")
    @app.get("/api/v1/health")
    def health():
        session = session_scope(db_url)
        try:
            session.execute(text("SELECT 1"))
            return jsonify({"status": "ok", "database": "ok"})
        finally:
            session.close()

    @app.get("/metrics")
    @app.get("/api/v1/metrics")
    def metrics():
        body, content_type = metrics_payload()
        return body, 200, {"Content-Type": content_type}

    @app.get("/products")
    @app.get("/api/v1/products")
    def products():
        limit, offset = _pagination()
        session = session_scope(db_url)
        try:
            query = select(Product).order_by(Product.updated_at.desc())
            category = request.args.get("category")
            search = request.args.get("q")
            if category:
                query = query.where(Product.category == category)
            if search:
                query = query.where(Product.title.ilike(f"%{search}%"))
            values = session.scalars(query.offset(offset).limit(limit)).unique().all()
            return jsonify(
                {
                    "items": [_product_json(product) for product in values],
                    "limit": limit,
                    "offset": offset,
                }
            )
        finally:
            session.close()

    @app.get("/products/<int:product_id>")
    @app.get("/api/v1/products/<int:product_id>")
    def product(product_id: int):
        session = session_scope(db_url)
        try:
            value = session.get(Product, product_id)
            if not value:
                return jsonify({"error": "product not found"}), 404
            return jsonify(_product_json(value))
        finally:
            session.close()

    @app.get("/trends")
    @app.get("/api/v1/trends")
    def trends():
        limit, offset = _pagination()
        session = session_scope(db_url)
        try:
            values = trend_signals(session)
            return jsonify(
                {"items": values[offset : offset + limit], "limit": limit, "offset": offset}
            )
        finally:
            session.close()

    @app.get("/runs")
    @app.get("/api/v1/runs")
    def runs():
        limit, offset = _pagination()
        session = session_scope(db_url)
        try:
            values = session.scalars(
                select(IngestionRun)
                .order_by(IngestionRun.started_at.desc())
                .offset(offset)
                .limit(limit)
            ).all()
            return jsonify(
                {
                    "items": [
                        {
                            "id": run.id,
                            "run_id": run.run_id,
                            "manifest_path": run.manifest_path,
                            "manifest_hash": run.manifest_hash,
                            "status": run.status,
                            "total": run.total_pages,
                            "succeeded": run.succeeded_pages,
                            "failed": run.failed_pages,
                            "fallbacks": run.fallback_pages,
                            "dead_letters": len(run.dead_letters),
                            "started_at": run.started_at.isoformat(),
                            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                        }
                        for run in values
                    ],
                    "limit": limit,
                    "offset": offset,
                }
            )
        finally:
            session.close()

    @app.get("/extractions")
    @app.get("/api/v1/extractions")
    def extractions():
        limit, offset = _pagination()
        session = session_scope(db_url)
        try:
            values = session.scalars(
                select(ExtractionRun)
                .order_by(ExtractionRun.created_at.desc())
                .offset(offset)
                .limit(limit)
            ).all()
            return jsonify(
                {
                    "items": [
                        {
                            "id": run.id,
                            "listing_id": run.listing_id,
                            "ingestion_run_id": run.ingestion_run_id,
                            "status": run.status,
                            "model": run.model,
                            "prompt_version": run.prompt_version,
                            "validation_errors": run.validation_errors,
                            "field_provenance": run.field_provenance,
                            "field_confidence": run.field_confidence,
                            "fallback_reason": run.fallback_reason,
                            "error": run.error,
                            "created_at": run.created_at.isoformat(),
                        }
                        for run in values
                    ],
                    "limit": limit,
                    "offset": offset,
                }
            )
        finally:
            session.close()

    @app.get("/match-candidates")
    @app.get("/api/v1/match-candidates")
    def match_candidates():
        limit, offset = _pagination()
        session = session_scope(db_url)
        try:
            values = session.scalars(
                select(ProductMatchCandidate)
                .order_by(ProductMatchCandidate.score.desc())
                .offset(offset)
                .limit(limit)
            ).all()
            return jsonify(
                {
                    "items": [
                        {
                            "id": candidate.id,
                            "source_listing_id": candidate.source_listing_id,
                            "candidate_product_id": candidate.candidate_product_id,
                            "score": candidate.score,
                            "method": candidate.method,
                            "status": candidate.status,
                            "created_at": candidate.created_at.isoformat(),
                        }
                        for candidate in values
                    ],
                    "limit": limit,
                    "offset": offset,
                }
            )
        finally:
            session.close()

    @app.get("/dead-letters")
    @app.get("/api/v1/dead-letters")
    def dead_letters():
        limit, offset = _pagination()
        session = session_scope(db_url)
        try:
            values = session.scalars(
                select(DeadLetter)
                .where(DeadLetter.resolved.is_(False))
                .order_by(DeadLetter.created_at.desc())
                .offset(offset)
                .limit(limit)
            ).all()
            return jsonify(
                {
                    "items": [
                        {
                            "id": dead.id,
                            "run_id": dead.ingestion_run_id,
                            "page_key": dead.page_key,
                            "source": dead.source,
                            "source_item_id": dead.source_item_id,
                            "url": dead.url,
                            "error": dead.error,
                            "resolved": dead.resolved,
                            "created_at": dead.created_at.isoformat(),
                        }
                        for dead in values
                    ],
                    "limit": limit,
                    "offset": offset,
                }
            )
        finally:
            session.close()

    @app.post("/dead-letters/<int:dead_letter_id>/resolve")
    @app.post("/api/v1/dead-letters/<int:dead_letter_id>/resolve")
    def resolve_dead_letter(dead_letter_id: int):
        from datetime import datetime, timezone

        session = session_scope(db_url)
        try:
            dead = session.get(DeadLetter, dead_letter_id)
            if not dead:
                return jsonify({"error": "dead letter not found"}), 404
            dead.resolved = True
            dead.resolved_at = datetime.now(timezone.utc)
            session.commit()
            return jsonify({"id": dead.id, "resolved": True})
        finally:
            session.close()

    @app.post("/match-candidates/<int:candidate_id>/decision")
    @app.post("/api/v1/match-candidates/<int:candidate_id>/decision")
    def decide_match_candidate(candidate_id: int):
        payload = request.get_json(silent=True) or {}
        decision = payload.get("decision")
        if decision not in {"accepted", "rejected"}:
            raise ValueError("decision must be 'accepted' or 'rejected'")
        session = session_scope(db_url)
        try:
            candidate = session.get(ProductMatchCandidate, candidate_id)
            if not candidate:
                return jsonify({"error": "match candidate not found"}), 404
            candidate.status = decision
            if decision == "accepted":
                candidate.source_listing.product_id = candidate.candidate_product_id
            session.commit()
            return jsonify(
                {
                    "id": candidate.id,
                    "decision": candidate.status,
                    "source_listing_id": candidate.source_listing_id,
                    "candidate_product_id": candidate.candidate_product_id,
                }
            )
        finally:
            session.close()

    return app

from __future__ import annotations

from flask import Flask, jsonify, request
from sqlalchemy import select

from marketplace.config import settings
from marketplace.db import initialize_database, session_scope
from marketplace.models import ExtractionRun, Observation, Product, SourceListing
from marketplace.trends import trend_signals


def _product_json(product: Product) -> dict:
    return {
        "id": product.id,
        "canonical_key": product.canonical_key,
        "title": product.title,
        "brand": product.brand,
        "model": product.model,
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
                    }
                    for observation in listing.observations
                ],
            }
            for listing in product.listings
        ],
    }


def create_app(database_url: str | None = None) -> Flask:
    app = Flask(__name__)
    db_url = database_url or settings.database_url
    initialize_database(db_url)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/products")
    def products():
        session = session_scope(db_url)
        try:
            query = select(Product).order_by(Product.updated_at.desc())
            category = request.args.get("category")
            if category:
                query = query.where(Product.category == category)
            values = session.scalars(query).unique().all()
            return jsonify([_product_json(product) for product in values])
        finally:
            session.close()

    @app.get("/products/<int:product_id>")
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
    def trends():
        session = session_scope(db_url)
        try:
            return jsonify(trend_signals(session))
        finally:
            session.close()

    @app.get("/runs")
    def runs():
        session = session_scope(db_url)
        try:
            values = session.scalars(select(ExtractionRun).order_by(ExtractionRun.created_at.desc())).all()
            return jsonify(
                [
                    {
                        "id": run.id,
                        "listing_id": run.listing_id,
                        "status": run.status,
                        "model": run.model,
                        "prompt_version": run.prompt_version,
                        "validation_errors": run.validation_errors,
                        "error": run.error,
                        "created_at": run.created_at.isoformat(),
                    }
                    for run in values
                ]
            )
        finally:
            session.close()

    return app

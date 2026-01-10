from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from marketplace.models import Observation, Product, SourceListing


def trend_signals(session: Session) -> list[dict]:
    rows = session.execute(
        select(
            Product.id,
            Product.title,
            Product.category,
            SourceListing.source,
            Observation.observed_at,
            Observation.price,
            Observation.availability,
            Observation.review_count,
        )
        .join(SourceListing, SourceListing.product_id == Product.id)
        .join(Observation, Observation.listing_id == SourceListing.id)
    ).all()
    if not rows:
        return []

    frame = pd.DataFrame(
        rows,
        columns=[
            "product_id",
            "title",
            "category",
            "source",
            "observed_at",
            "price",
            "availability",
            "review_count",
        ],
    )
    frame["is_available"] = (
        frame["availability"]
        .fillna("")
        .str.lower()
        .str.contains("in ?stock|available|buy", regex=True)
    )
    results = []
    for product_id, group in frame.groupby("product_id"):
        ordered = group.sort_values("observed_at")
        prices = ordered["price"].dropna()
        reviews = ordered["review_count"].dropna()
        first_price = float(prices.iloc[0]) if len(prices) else None
        last_price = float(prices.iloc[-1]) if len(prices) else None
        price_change_pct = ((last_price - first_price) / first_price * 100) if first_price else None
        review_growth = int(reviews.iloc[-1] - reviews.iloc[0]) if len(reviews) >= 2 else 0
        source_count = int(group["source"].nunique())
        availability_rate = float(group["is_available"].mean())
        score = round(
            min(100.0, source_count * 20 + availability_rate * 30 + min(max(review_growth, 0), 50)),
            2,
        )
        results.append(
            {
                "product_id": int(product_id),
                "title": group["title"].iloc[0],
                "category": group["category"].iloc[0],
                "sources": sorted(group["source"].unique().tolist()),
                "observation_count": len(group),
                "review_growth": review_growth,
                "price_change_pct": price_change_pct,
                "availability_rate": availability_rate,
                "trend_score": score,
            }
        )
    return sorted(results, key=lambda item: item["trend_score"], reverse=True)

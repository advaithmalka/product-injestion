from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from marketplace.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    brand: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    gtin: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    manufacturer_part_number: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True, index=True
    )
    category: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    listings: Mapped[list["SourceListing"]] = relationship(back_populates="product")
    match_candidates: Mapped[list["ProductMatchCandidate"]] = relationship(
        back_populates="candidate_product",
        foreign_keys="ProductMatchCandidate.candidate_product_id",
    )


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    manifest_path: Mapped[str] = mapped_column(String(1000))
    manifest_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    total_pages: Mapped[int] = mapped_column(Integer, default=0)
    succeeded_pages: Mapped[int] = mapped_column(Integer, default=0)
    failed_pages: Mapped[int] = mapped_column(Integer, default=0)
    fallback_pages: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    page_attempts: Mapped[list["PageAttempt"]] = relationship(back_populates="ingestion_run")
    dead_letters: Mapped[list["DeadLetter"]] = relationship(back_populates="ingestion_run")


class PageAttempt(Base):
    __tablename__ = "page_attempts"
    __table_args__ = (
        UniqueConstraint("ingestion_run_id", "page_key", "attempt_number", name="uq_page_attempt"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ingestion_run_id: Mapped[int] = mapped_column(ForeignKey("ingestion_runs.id"), index=True)
    page_key: Mapped[str] = mapped_column(String(255), index=True)
    source: Mapped[str] = mapped_column(String(50))
    source_item_id: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(1000))
    attempt_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), index=True)
    raw_html_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    ingestion_run: Mapped[IngestionRun] = relationship(back_populates="page_attempts")


class DeadLetter(Base):
    __tablename__ = "dead_letters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ingestion_run_id: Mapped[int] = mapped_column(ForeignKey("ingestion_runs.id"), index=True)
    page_attempt_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("page_attempts.id"), nullable=True
    )
    page_key: Mapped[str] = mapped_column(String(255), index=True)
    source: Mapped[str] = mapped_column(String(50))
    source_item_id: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(1000))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    ingestion_run: Mapped[IngestionRun] = relationship(back_populates="dead_letters")


class SourceListing(Base):
    __tablename__ = "source_listings"
    __table_args__ = (UniqueConstraint("source", "source_item_id", name="uq_source_item"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(50), index=True)
    source_item_id: Mapped[str] = mapped_column(String(255), index=True)
    url: Mapped[str] = mapped_column(String(1000))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    title: Mapped[str] = mapped_column(String(500))
    raw_html_path: Mapped[str] = mapped_column(String(1000))
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    product: Mapped[Product] = relationship(back_populates="listings")
    observations: Mapped[list["Observation"]] = relationship(back_populates="listing")
    extraction_runs: Mapped[list["ExtractionRun"]] = relationship(back_populates="listing")
    match_candidates: Mapped[list["ProductMatchCandidate"]] = relationship(
        back_populates="source_listing"
    )


class ProductMatchCandidate(Base):
    __tablename__ = "product_match_candidates"
    __table_args__ = (
        UniqueConstraint("source_listing_id", "candidate_product_id", name="uq_match_candidate"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_listing_id: Mapped[int] = mapped_column(ForeignKey("source_listings.id"), index=True)
    candidate_product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    score: Mapped[float] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    source_listing: Mapped[SourceListing] = relationship(back_populates="match_candidates")
    candidate_product: Mapped[Product] = relationship(
        back_populates="match_candidates", foreign_keys=[candidate_product_id]
    )


class Observation(Base):
    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("source_listings.id"), index=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    availability: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    condition: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    review_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    listing: Mapped[SourceListing] = relationship(back_populates="observations")


class ExtractionRun(Base):
    __tablename__ = "extraction_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    listing_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("source_listings.id"), nullable=True, index=True
    )
    ingestion_run_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("ingestion_runs.id"), nullable=True, index=True
    )
    page_attempt_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("page_attempts.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(30), index=True)
    model: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(50), default="v1")
    raw_response: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    validation_errors: Mapped[list[str]] = mapped_column(JSON, default=list)
    field_provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    field_confidence: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    fallback_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    listing: Mapped[Optional[SourceListing]] = relationship(back_populates="extraction_runs")

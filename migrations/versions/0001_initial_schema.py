"""Initial marketplace product intelligence schema."""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("canonical_key", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("brand", sa.String(length=200)),
        sa.Column("model", sa.String(length=200)),
        sa.Column("gtin", sa.String(length=50)),
        sa.Column("manufacturer_part_number", sa.String(length=200)),
        sa.Column("category", sa.String(length=200)),
        sa.Column("description", sa.Text()),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("canonical_key"),
    )
    op.create_index("ix_products_canonical_key", "products", ["canonical_key"], unique=False)
    op.create_index("ix_products_gtin", "products", ["gtin"], unique=False)
    op.create_index(
        "ix_products_manufacturer_part_number",
        "products",
        ["manufacturer_part_number"],
        unique=False,
    )

    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(length=80), nullable=False),
        sa.Column("manifest_path", sa.String(length=1000), nullable=False),
        sa.Column("manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("total_pages", sa.Integer(), nullable=False),
        sa.Column("succeeded_pages", sa.Integer(), nullable=False),
        sa.Column("failed_pages", sa.Integer(), nullable=False),
        sa.Column("fallback_pages", sa.Integer(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("run_id"),
    )
    op.create_index("ix_ingestion_runs_run_id", "ingestion_runs", ["run_id"], unique=False)
    op.create_index(
        "ix_ingestion_runs_manifest_hash", "ingestion_runs", ["manifest_hash"], unique=False
    )
    op.create_index("ix_ingestion_runs_status", "ingestion_runs", ["status"], unique=False)

    op.create_table(
        "page_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "ingestion_run_id", sa.Integer(), sa.ForeignKey("ingestion_runs.id"), nullable=False
        ),
        sa.Column("page_key", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("source_item_id", sa.String(length=255), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("raw_html_path", sa.String(length=1000)),
        sa.Column("error", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "ingestion_run_id", "page_key", "attempt_number", name="uq_page_attempt"
        ),
    )
    op.create_index(
        "ix_page_attempts_ingestion_run_id", "page_attempts", ["ingestion_run_id"], unique=False
    )
    op.create_index("ix_page_attempts_page_key", "page_attempts", ["page_key"], unique=False)
    op.create_index("ix_page_attempts_status", "page_attempts", ["status"], unique=False)

    op.create_table(
        "dead_letters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "ingestion_run_id", sa.Integer(), sa.ForeignKey("ingestion_runs.id"), nullable=False
        ),
        sa.Column("page_attempt_id", sa.Integer(), sa.ForeignKey("page_attempts.id")),
        sa.Column("page_key", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("source_item_id", sa.String(length=255), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("resolved", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_dead_letters_ingestion_run_id", "dead_letters", ["ingestion_run_id"], unique=False
    )
    op.create_index("ix_dead_letters_page_key", "dead_letters", ["page_key"], unique=False)
    op.create_index("ix_dead_letters_resolved", "dead_letters", ["resolved"], unique=False)

    op.create_table(
        "source_listings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("source_item_id", sa.String(length=255), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("raw_html_path", sa.String(length=1000), nullable=False),
        sa.Column("source_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source", "source_item_id", name="uq_source_item"),
    )
    op.create_index("ix_source_listings_source", "source_listings", ["source"], unique=False)
    op.create_index(
        "ix_source_listings_source_item_id", "source_listings", ["source_item_id"], unique=False
    )
    op.create_index(
        "ix_source_listings_product_id", "source_listings", ["product_id"], unique=False
    )

    op.create_table(
        "product_match_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "source_listing_id", sa.Integer(), sa.ForeignKey("source_listings.id"), nullable=False
        ),
        sa.Column(
            "candidate_product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False
        ),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("method", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_listing_id", "candidate_product_id", name="uq_match_candidate"),
    )
    op.create_index(
        "ix_product_match_candidates_source_listing_id",
        "product_match_candidates",
        ["source_listing_id"],
        unique=False,
    )
    op.create_index(
        "ix_product_match_candidates_candidate_product_id",
        "product_match_candidates",
        ["candidate_product_id"],
        unique=False,
    )
    op.create_index(
        "ix_product_match_candidates_status", "product_match_candidates", ["status"], unique=False
    )

    op.create_table(
        "observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("listing_id", sa.Integer(), sa.ForeignKey("source_listings.id"), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price", sa.Float()),
        sa.Column("currency", sa.String(length=10)),
        sa.Column("availability", sa.String(length=100)),
        sa.Column("condition", sa.String(length=100)),
        sa.Column("review_count", sa.Integer()),
        sa.Column("rating", sa.Float()),
        sa.Column("attributes", sa.JSON(), nullable=False),
    )
    op.create_index("ix_observations_listing_id", "observations", ["listing_id"], unique=False)
    op.create_index("ix_observations_observed_at", "observations", ["observed_at"], unique=False)

    op.create_table(
        "extraction_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("listing_id", sa.Integer(), sa.ForeignKey("source_listings.id")),
        sa.Column("ingestion_run_id", sa.Integer(), sa.ForeignKey("ingestion_runs.id")),
        sa.Column("page_attempt_id", sa.Integer(), sa.ForeignKey("page_attempts.id")),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("model", sa.String(length=200)),
        sa.Column("prompt_version", sa.String(length=50), nullable=False),
        sa.Column("raw_response", sa.JSON()),
        sa.Column("validation_errors", sa.JSON(), nullable=False),
        sa.Column("field_provenance", sa.JSON(), nullable=False),
        sa.Column("field_confidence", sa.JSON(), nullable=False),
        sa.Column("fallback_reason", sa.Text()),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_extraction_runs_listing_id", "extraction_runs", ["listing_id"], unique=False
    )
    op.create_index(
        "ix_extraction_runs_ingestion_run_id", "extraction_runs", ["ingestion_run_id"], unique=False
    )
    op.create_index(
        "ix_extraction_runs_page_attempt_id", "extraction_runs", ["page_attempt_id"], unique=False
    )
    op.create_index("ix_extraction_runs_status", "extraction_runs", ["status"], unique=False)
    op.create_index(
        "ix_extraction_runs_created_at", "extraction_runs", ["created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_table("extraction_runs")
    op.drop_table("observations")
    op.drop_table("product_match_candidates")
    op.drop_table("source_listings")
    op.drop_table("dead_letters")
    op.drop_table("page_attempts")
    op.drop_table("ingestion_runs")
    op.drop_table("products")

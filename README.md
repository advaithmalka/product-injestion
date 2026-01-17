# Marketplace Product Intelligence

A small, data-engineering-focused system that collects marketplace product HTML, turns listings into a canonical product model, and exposes cross-source trend signals.

The first milestone is intentionally local and fixture-driven. Selenium supports live page collection when permitted, but automated tests use saved HTML fixtures and never depend on marketplace availability.

## What is implemented

- Versioned JSON/CSV page manifests
- Fixture and Selenium collectors behind one interface
- Marketplace-aware HTML parsing with JSON-LD, OpenGraph, and visible-text fallbacks
- Optional LLM extraction through an OpenAI-compatible API
- Local Pydantic validation and deterministic normalization
- Product identity matching using identifiers, brand/model, and normalized titles
- SQLite by default; PostgreSQL can be used through `DATABASE_URL`
- Raw HTML evidence plus extraction metadata
- Flask endpoints for products, observations, extraction runs, and trend signals
- Pandas-based trend signal calculation

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
pytest
marketplace-ingest --manifest examples/manifest.json
flask --app marketplace.app run --debug
```

The sample manifest uses local HTML fixtures, so the ingestion command works without Selenium or an API key.

## PostgreSQL and Docker

The API and database can run together with Docker Compose:

```bash
cp .env.example .env
# Add OPENAI_API_KEY and OPENAI_MODEL to .env for LLM runs.
docker compose up --build
```

The API is available at `http://127.0.0.1:8000`. PostgreSQL data is persisted in the `postgres_data` volume and raw HTML is mounted at `./data`. Do not commit `.env` or paste resolved Compose configuration into logs because it contains secrets.

To run a fixture ingestion against the Compose database from inside the API container:

```bash
docker compose exec api marketplace-ingest --manifest examples/manifest.json
```

The container runs `alembic upgrade head` before Gunicorn starts. Use a stable `--run-id` when a batch should be idempotent; a completed run with the same ID is returned without duplicating observations.

To run the optional LLM extraction experiment, put your key in `.env`, set `OPENAI_MODEL` to a model available at the compatible endpoint, and run:

```bash
marketplace-ingest --manifest examples/manifest.json --with-llm
```

The client accepts `OPENAI_BASE_URL`. ARC's web host (`https://llm.arc.vt.edu/`) is automatically mapped to its documented API host (`https://llm-api.arc.vt.edu/api/v1`); new `.env` files should use the API host directly. If another compatible service exposes a different path, set that complete path in `.env`.

## API examples

```bash
curl http://127.0.0.1:5000/health
curl http://127.0.0.1:5000/products
curl http://127.0.0.1:5000/trends
curl http://127.0.0.1:5000/runs
```

Additional operational endpoints include `/metrics`, `/extractions`, `/match-candidates`, and `/dead-letters`. Operators can resolve dead letters or accept/reject fuzzy match candidates through the corresponding POST endpoints. Extraction evaluation can be run locally with:

```bash
marketplace-evaluate --gold examples/gold_extractions.json
```

The parser/normalizer stage can be measured independently with a replay benchmark:

```bash
marketplace-benchmark --manifest examples/manifest.json --events 150000
```

This measures 150,000 replayed fixture events, not 150,000 live requests or LLM calls. Keep those boundaries explicit in resume claims.

## Resume-worthy extension path

The next improvements should be measured rather than claimed: add a small labeled extraction set, report per-field validation accuracy, add retry/dead-letter metrics, and then introduce a queue or scheduled execution only when the batch workflow is reliable.

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

## Resume-worthy extension path

The next improvements should be measured rather than claimed: add a small labeled extraction set, report per-field validation accuracy, add retry/dead-letter metrics, and then introduce a queue or scheduled execution only when the batch workflow is reliable.

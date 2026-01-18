# Marketplace Product Intelligence

An extensible marketplace data-ingestion and product-intelligence pipeline for collecting product pages from multiple sources, normalizing inconsistent listing data, and producing cross-marketplace trend signals.

The project is intentionally built as a small but production-shaped data-engineering system. It uses saved HTML fixtures for deterministic development and testing, while exposing the same collector interface for permitted Selenium-based page collection. An OpenAI-compatible model can enrich deterministic extraction, but the model is treated as an untrusted data source: every response is schema-validated, provenance is retained, and the parser remains a fallback.

## Why this project exists

Marketplace data is difficult to compare because each source has different HTML structures, identifiers, prices, availability labels, and product naming conventions. This project separates three concepts that are often incorrectly collapsed into one record:

1. A canonical product, such as “Aurora A-100 Wireless Headphones.”
2. A source listing, such as the eBay or Amazon page selling that product.
3. A time-stamped observation, such as the price, availability, rating, and review count seen on a particular run.

That separation makes it possible to track price changes, compare marketplace coverage, detect growing products, and audit exactly where each field came from.

## Architecture

```text
JSON/CSV manifest
        |
        v
Fixture collector or Selenium collector
        |
        v
Raw HTML evidence -----> deterministic marketplace parser
        |                              |
        |                              v
        +----------------------> optional LLM enrichment
                                       |
                                       v
                         Pydantic schema validation
                                       |
                                       v
                         normalized product extraction
                                       |
          +----------------------------+-----------------------------+
          |                            |                             |
          v                            v                             v
   PostgreSQL/SQLite             retry + DLQ                 metrics + logs
          |
          v
 Products, listings, observations, extraction runs, match candidates
          |
          v
 Flask API and Pandas trend signals
```

## What is implemented

- Versioned JSON/CSV page manifests
- Fixture and Selenium collectors behind one interface
- Marketplace-aware HTML parsing with JSON-LD, OpenGraph, and visible-text fallbacks
- Optional LLM extraction through an OpenAI-compatible API
- Local Pydantic validation and deterministic normalization
- Product identity matching using identifiers, brand/model, and normalized titles
- SQLite by default; PostgreSQL can be used through `DATABASE_URL`
- Raw HTML evidence plus extraction metadata
- Durable ingestion runs with retries, idempotency, page attempts, and dead-letter recovery
- Prometheus metrics and structured JSON logs for ingestion/LLM operations
- Fuzzy match candidates with operator accept/reject decisions
- Flask endpoints for products, observations, extraction runs, and trend signals
- Pandas-based trend signal calculation
- Gold-set extraction evaluation with per-field accuracy

## Data flow

1. A JSON or CSV manifest identifies a source, URL, optional source-item ID, and optional local HTML path.
2. A collector obtains saved fixture HTML or a permitted live page through headless Selenium.
3. The pipeline stores raw HTML evidence and records every collection attempt.
4. The deterministic parser extracts product fields using JSON-LD, OpenGraph, source selectors, and visible text.
5. An optional OpenAI-compatible LLM enriches the baseline extraction with structured JSON.
6. Pydantic validates the result; null or failed LLM fields do not erase reliable parser fields.
7. The pipeline resolves a canonical product, upserts a source listing, writes an observation, and stores extraction provenance.
8. Pandas computes cross-source trend signals, while Flask exposes data and operational controls.

## Reliability guarantees

- Stable `--run-id` values make completed batches idempotent.
- Transient collection and LLM errors use bounded retries with exponential backoff.
- Exhausted pages become dead letters instead of silently disappearing.
- Page attempts, manifest hashes, raw HTML paths, model responses, fallback reasons, and field provenance are persisted.
- Fuzzy matches become reviewable candidates instead of causing an irreversible automatic merge.
- Prometheus counters and structured JSON logs expose throughput, retry, fallback, and failure behavior.

## Repository layout

```text
marketplace/
  api.py             Flask routes and operational endpoints
  benchmark.py       parser/normalizer replay benchmark
  cli.py             marketplace-ingest command
  collectors.py      fixture and Selenium collectors
  config.py          environment-backed settings and ARC URL normalization
  db.py              SQLAlchemy engine/session setup
  evaluation.py      labeled extraction evaluation command
  llm.py             OpenAI-compatible structured extraction client
  models.py          SQLAlchemy persistence models
  normalization.py   canonical keys and normalized text
  observability.py   JSON logging and Prometheus metrics
  parsing.py         deterministic HTML extraction
  pipeline.py        retries, persistence, matching, and orchestration
  schemas.py         Pydantic extraction and manifest schemas
  trends.py          Pandas-based trend signal calculations
migrations/          Alembic environment and schema revisions
examples/             sample manifest, fixtures, and gold extraction set
tests/                deterministic unit and integration-style tests
docs/adr/             architecture decision records
```

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

The sample manifest uses local HTML fixtures, so the ingestion command works without Selenium, PostgreSQL, network access, or an API key. The local default database is `marketplace.db`.

To use a local PostgreSQL instance instead, set `DATABASE_URL` before starting the application:

```bash
export DATABASE_URL='postgresql+psycopg://marketplace:marketplace@localhost:5432/marketplace'
marketplace-ingest --manifest examples/manifest.json
```

## PostgreSQL and Docker

The primary runtime is a two-service Docker Compose deployment:

- `db`: PostgreSQL 16 Alpine with a persistent `postgres_data` volume.
- `api`: Python 3.11 with Chromium, Selenium, Gunicorn, Alembic, and the Flask application.

The API waits for PostgreSQL health, runs `alembic upgrade head`, and then starts Gunicorn with two workers. Raw HTML is mounted at `./data/raw` so evidence survives container replacement.

```bash
cp .env.example .env
# Add OPENAI_API_KEY and OPENAI_MODEL to .env for LLM runs.
docker compose up --build -d
docker compose ps
curl http://127.0.0.1:8000/health
```

The API is available at `http://127.0.0.1:8000`. PostgreSQL data is persisted in the `postgres_data` volume and raw HTML is mounted at `./data`. Do not commit `.env` or paste resolved Compose configuration into logs because it contains secrets.

To run a fixture ingestion against the Compose database from inside the API container:

```bash
docker compose exec api marketplace-ingest \
  --manifest examples/manifest.json \
  --run-id fixture-demo-001
```

The container runs `alembic upgrade head` before Gunicorn starts. Use a stable `--run-id` when a batch should be idempotent; a completed run with the same ID is returned without duplicating observations. Run `docker compose down` to stop the services while preserving the database volume; do not use `docker compose down -v` unless deleting local data is intentional.

To run the optional LLM extraction experiment, put your key in `.env`, set `OPENAI_MODEL` to a model available at the compatible endpoint, and run:

```bash
marketplace-ingest \
  --manifest examples/manifest.json \
  --with-llm \
  --max-retries 2 \
  --run-id llm-demo-001
```

The client accepts `OPENAI_BASE_URL`. ARC's web host (`https://llm.arc.vt.edu/`) is automatically mapped to its documented API host (`https://llm-api.arc.vt.edu/api/v1`); new `.env` files should use the API host directly. If another compatible service exposes a different path, set that complete path in `.env`.

## Environment variables

Copy `.env.example` to `.env`. The `.env` file is ignored by Git and must never be committed.

| Variable | Purpose | Example |
| --- | --- | --- |
| `DATABASE_URL` | SQLAlchemy database URL for local execution | `sqlite:///marketplace.db` |
| `RAW_HTML_DIR` | Directory for raw page evidence | `data/raw` |
| `OPENAI_API_KEY` | API credential for optional LLM extraction | set locally only |
| `OPENAI_BASE_URL` | OpenAI-compatible API base URL | `https://llm-api.arc.vt.edu/api/v1` |
| `OPENAI_MODEL` | Model name exposed by the provider | `DeepSeek-V4.1-Flash` |
| `AUTO_CREATE_SCHEMA` | Local convenience schema creation; disabled in Compose | `true` |

ARC's web host is normalized by the client to its API host. Never print resolved Compose configuration because it expands secrets from `.env`.

## Manifest format

JSON manifests are arrays of page objects. CSV manifests use the same field names as columns.

```json
[
  {
    "source": "ebay",
    "url": "https://example.test/listing/aurora-a100",
    "html_path": "fixtures/ebay/aurora-headphones.html",
    "source_item_id": "ebay-aurora-a100",
    "category": "electronics"
  }
]
```

`html_path` is resolved relative to the manifest file. If `source_item_id` is omitted, a stable hash of the URL is used. A stable source-item ID with different snapshot URLs allows multiple observations for a listing across runs.

For live collection, omit `html_path` and pass `--live`:

```bash
marketplace-ingest --manifest examples/live-manifest.json --live
```

Only collect pages you are permitted to access. Respect marketplace terms, robots guidance, rate limits, authentication requirements, and applicable law. The included tests use saved synthetic fixtures and do not scrape Amazon or eBay.

## API examples

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/products
curl http://127.0.0.1:8000/trends
curl http://127.0.0.1:8000/runs
```

All endpoints are also available under the `/api/v1` prefix. List endpoints accept `limit` and `offset`; `/products` also accepts `q` and `category`.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Database liveness check |
| `GET` | `/metrics` | Prometheus metrics |
| `GET` | `/products` | Canonical products with listings and observations |
| `GET` | `/products/<id>` | One canonical product |
| `GET` | `/trends` | Cross-source trend signals |
| `GET` | `/runs` | Ingestion-run summaries |
| `GET` | `/extractions` | LLM/baseline extraction audit records |
| `GET` | `/match-candidates` | Fuzzy match candidates |
| `GET` | `/dead-letters` | Unresolved failed pages |
| `POST` | `/dead-letters/<id>/resolve` | Mark a dead letter resolved |
| `POST` | `/match-candidates/<id>/decision` | Accept or reject a candidate |

Example operational calls:

```bash
curl 'http://127.0.0.1:8000/products?limit=10&q=headphones'
curl 'http://127.0.0.1:8000/dead-letters?limit=50'
curl -X POST http://127.0.0.1:8000/dead-letters/1/resolve
curl -X POST http://127.0.0.1:8000/match-candidates/1/decision \
  -H 'Content-Type: application/json' \
  -d '{"decision":"accepted"}'
```

Extraction evaluation can be run locally with:

```bash
marketplace-evaluate --gold examples/gold_extractions.json
```

The parser/normalizer stage can be measured independently with a replay benchmark:

```bash
marketplace-benchmark --manifest examples/manifest.json --events 150000
```

This measures 150,000 replayed fixture events, not 150,000 live requests or LLM calls. Keep those boundaries explicit in resume claims.

## Testing and quality checks

```bash
pytest -q
ruff check .
ruff format --check .
docker compose config --quiet
```

The test suite covers parser behavior, schema validation, source normalization, retry handling, dead letters, idempotent runs, fuzzy match candidates, API pagination and errors, extraction evaluation, and the replay benchmark.

## Resume-ready project description

- Built a Dockerized marketplace product-ingestion platform backed by PostgreSQL and Alembic, with pluggable eBay/Amazon HTML collectors, raw-page provenance, and canonical product/listing/observation modeling.
- Integrated an OpenAI-compatible DeepSeek model to transform semi-structured marketplace HTML into validated JSON metadata, preserving field-level provenance and falling back to deterministic parsing when model extraction fails.
- Engineered retryable, idempotent batch ingestion with page-attempt history, exponential backoff, dead-letter recovery, structured logs, and Prometheus metrics for operational visibility.
- Implemented identifier- and fuzzy-title-based product matching plus reviewable operator decisions, and exposed products, trends, ingestion runs, extraction audits, and recovery controls through a versioned Flask API.
- Benchmarked the parser/normalizer stage across 150,000 replayed fixture events with 100% success and approximately 3,813 events/second, alongside a gold-set evaluator for per-field extraction accuracy.

Keep the benchmark wording precise: the current 150,000-event result is a replay benchmark, not a claim of 150,000 live marketplace interactions.

## Roadmap

The current milestone is a reliable, auditable batch system. Natural next steps are:

1. Add a queue/worker boundary for parallel collection and bounded LLM concurrency.
2. Add scheduled runs and incremental manifest generation.
3. Add authenticated operational endpoints and secret-management integration.
4. Add CI with a real PostgreSQL service, migration checks, and container smoke tests.
5. Expand the labeled evaluation set and measure live-source quality only on permitted data.
6. Deploy the Compose-shaped services to AWS EC2 or a managed container platform after local behavior is stable.

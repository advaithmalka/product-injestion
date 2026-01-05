import json
from pathlib import Path

from marketplace.collectors import FixturePageCollector
from marketplace.config import Settings
from marketplace.db import session_scope
from marketplace.models import ExtractionRun, Observation, Product, SourceListing
from marketplace.llm import LLMResult
from marketplace.pipeline import run_ingestion
from marketplace.schemas import ProductExtraction
from marketplace.trends import trend_signals


class FlakyCollector:
    def __init__(self, html):
        self.html = html
        self.calls = 0

    def collect(self, url, html_path=None):
        self.calls += 1
        if self.calls == 1:
            raise TimeoutError("temporary source timeout")
        return self.html


class MinimalExtractor:
    def extract(self, source, url, html):
        return LLMResult(
            extraction=ProductExtraction(title="Aurora Wireless Headphones"),
            raw_response={"content": '{"title":"Aurora Wireless Headphones"}'},
            model="test-model",
        )


def test_fixture_ingestion_is_reproducible(tmp_path):
    manifest = json.loads(Path("examples/manifest.json").read_text())
    db_path = tmp_path / "test.db"
    config = Settings(database_url=f"sqlite:///{db_path}", raw_html_dir=str(tmp_path / "raw"))
    result = run_ingestion("examples/manifest.json", FixturePageCollector(), config)

    assert result["succeeded"] == 3
    assert result["failed"] == 0
    session = session_scope(config.database_url)
    try:
        assert session.query(Product).count() == 1
        assert session.query(SourceListing).count() == 2
        assert session.query(Observation).count() == 3
        assert session.query(ExtractionRun).count() == 3
        assert all(Path(path).exists() for path, in session.query(SourceListing.raw_html_path).all())
        signals = trend_signals(session)
        assert signals[0]["sources"] == ["amazon", "ebay"]
        assert signals[0]["review_growth"] == 10
        assert signals[0]["availability_rate"] == 1.0
    finally:
        session.close()


def test_transient_collection_failure_is_retried(tmp_path):
    html = Path("tests/fixtures/ebay/aurora-headphones.html").read_text()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([{"source": "ebay", "url": "https://example.test/item"}]))
    db_path = tmp_path / "retry.db"
    config = Settings(database_url=f"sqlite:///{db_path}", raw_html_dir=str(tmp_path / "raw"))
    result = run_ingestion(manifest, FlakyCollector(html), config, max_retries=1)

    assert result["succeeded"] == 1
    assert result["failed"] == 0


def test_llm_nulls_do_not_erase_parser_fields(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "source": "ebay",
                    "url": "https://example.test/item",
                    "html_path": str(Path("tests/fixtures/ebay/aurora-headphones.html").resolve()),
                }
            ]
        )
    )
    config = Settings(database_url=f"sqlite:///{tmp_path / 'merge.db'}", raw_html_dir=str(tmp_path / "raw"))
    result = run_ingestion(manifest, FixturePageCollector(), config, MinimalExtractor(), max_retries=0)

    assert result["succeeded"] == 1
    session = session_scope(config.database_url)
    try:
        product = session.query(Product).one()
        observation = session.query(Observation).one()
        assert product.brand == "Aurora"
        assert product.model == "A-100"
        assert observation.price == 79.99
    finally:
        session.close()

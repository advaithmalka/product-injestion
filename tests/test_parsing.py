from pathlib import Path

from marketplace.parsing import parse_html


def test_parse_json_ld_product():
    html = Path("tests/fixtures/ebay/aurora-headphones.html").read_text()
    result = parse_html("ebay", html, "https://example.test/item")
    assert result.title == "Aurora Wireless Headphones"
    assert result.price == 79.99
    assert result.currency == "USD"
    assert result.review_count == 120

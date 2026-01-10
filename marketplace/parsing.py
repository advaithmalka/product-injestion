from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup

from marketplace.schemas import ProductExtraction

SOURCE_SELECTORS = {
    "ebay": {
        "title": ["#itemTitle", "h1"],
        "price": [".x-price-primary", "[data-price]", ".price"],
        "availability": [".d-quantity__availability", "[data-availability]", ".availability"],
        "review_count": [".reviews", "[data-review-count]"],
    },
    "amazon": {
        "title": ["#productTitle", "h1"],
        "price": [".a-price .a-offscreen", "[data-price]", ".price"],
        "availability": ["#availability", "[data-availability]", ".availability"],
        "review_count": ["#acrCustomerReviewText", "[data-review-count]"],
    },
}


def _first_text(soup: BeautifulSoup, selectors: list[str]) -> str | None:
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            value = node.get("content") or node.get_text(" ", strip=True)
            if value:
                return value.strip()
    return None


def _json_ld(soup: BeautifulSoup) -> dict[str, Any]:
    for node in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(node.string or node.get_text())
        except (TypeError, json.JSONDecodeError):
            continue
        candidates = payload if isinstance(payload, list) else [payload]
        for item in candidates:
            if isinstance(item, dict) and (item.get("@type") == "Product" or "offers" in item):
                return item
    return {}


def _number(value: Any) -> float | None:
    if value is None:
        return None
    match = re.search(r"\d[\d,]*(?:\.\d+)?", str(value))
    return float(match.group(0).replace(",", "")) if match else None


def parse_html(source: str, html: str, url: str) -> ProductExtraction:
    """Extract a safe baseline before optional LLM enrichment."""
    soup = BeautifulSoup(html, "html.parser")
    ld = _json_ld(soup)
    offers = ld.get("offers", {}) if isinstance(ld.get("offers"), dict) else {}
    aggregate = ld.get("aggregateRating", {}) if isinstance(ld.get("aggregateRating"), dict) else {}
    selectors = SOURCE_SELECTORS.get(source.lower(), {})
    title = ld.get("name") or _first_text(
        soup, selectors.get("title", []) + ["meta[property='og:title']", "title"]
    )
    if not title:
        raise ValueError(f"Could not find a title for {url}")

    brand = ld.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name")
    identifier = ld.get("gtin13") or ld.get("gtin12") or ld.get("gtin")
    extracted = {
        "title": str(title),
        "brand": brand or _first_text(soup, ["[data-brand]", ".brand"]),
        "model": ld.get("model") or _first_text(soup, ["[data-model]", ".model"]),
        "category": ld.get("category") or _first_text(soup, ["[data-category]", ".category"]),
        "description": ld.get("description")
        or _first_text(soup, ["meta[name='description']", ".description"]),
        "price": _number(offers.get("price"))
        or _number(_first_text(soup, selectors.get("price", []) + ["[data-price]", ".price"])),
        "currency": offers.get("priceCurrency")
        or _first_text(soup, ["[data-currency]", ".currency"]),
        "availability": offers.get("availability")
        or _first_text(
            soup, selectors.get("availability", []) + ["[data-availability]", ".availability"]
        ),
        "condition": offers.get("itemCondition")
        or _first_text(soup, ["[data-condition]", ".condition"]),
        "review_count": int(aggregate["reviewCount"])
        if aggregate.get("reviewCount")
        else _number(_first_text(soup, selectors.get("review_count", []))),
        "rating": _number(aggregate.get("ratingValue")),
        "gtin": str(identifier) if identifier else None,
        "manufacturer_part_number": ld.get("mpn") or _first_text(soup, ["[data-mpn]", ".mpn"]),
    }
    method = "json-ld" if ld else "html-selector"
    evidence = {
        field: {"method": method, "source": source, "url": url, "value": str(value)}
        for field, value in extracted.items()
        if value is not None
    }
    confidence = {field: 1.0 if method == "json-ld" else 0.7 for field in evidence}
    return ProductExtraction(
        **extracted,
        attributes={"source": source, "url": url},
        evidence=evidence,
        confidence=confidence,
    )


def visible_text(html: str, max_chars: int = 12000) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript"]):
        node.decompose()
    return " ".join(soup.get_text(" ", strip=True).split())[:max_chars]

from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup

from marketplace.schemas import ProductExtraction


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
    title = ld.get("name") or _first_text(soup, ["h1", "meta[property='og:title']", "title"])
    if not title:
        raise ValueError(f"Could not find a title for {url}")

    brand = ld.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name")
    identifier = ld.get("gtin13") or ld.get("gtin12") or ld.get("gtin")
    return ProductExtraction(
        title=str(title),
        brand=brand or _first_text(soup, ["[data-brand]", ".brand"]),
        model=ld.get("model") or _first_text(soup, ["[data-model]", ".model"]),
        category=ld.get("category") or _first_text(soup, ["[data-category]", ".category"]),
        description=ld.get("description") or _first_text(soup, ["meta[name='description']", ".description"]),
        price=_number(offers.get("price")) or _number(_first_text(soup, ["[data-price]", ".price"])),
        currency=offers.get("priceCurrency") or _first_text(soup, ["[data-currency]", ".currency"]),
        availability=offers.get("availability") or _first_text(soup, ["[data-availability]", ".availability"]),
        condition=offers.get("itemCondition") or _first_text(soup, ["[data-condition]", ".condition"]),
        review_count=int(aggregate["reviewCount"]) if aggregate.get("reviewCount") else None,
        rating=_number(aggregate.get("ratingValue")),
        gtin=str(identifier) if identifier else None,
        attributes={"source": source, "url": url},
    )


def visible_text(html: str, max_chars: int = 12000) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript"]):
        node.decompose()
    return " ".join(soup.get_text(" ", strip=True).split())[:max_chars]

from __future__ import annotations

import re
import unicodedata

from marketplace.schemas import ProductExtraction


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def canonical_key(extraction: ProductExtraction) -> str:
    if extraction.gtin:
        return f"gtin:{normalize_text(extraction.gtin)}"
    if extraction.brand and extraction.model:
        return f"brand-model:{normalize_text(extraction.brand)}:{normalize_text(extraction.model)}"
    return f"title:{normalize_text(extraction.title)}"

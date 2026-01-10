from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProductExtraction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(min_length=1)
    brand: Optional[str] = None
    model: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    price: Optional[float] = Field(default=None, ge=0)
    currency: Optional[str] = None
    availability: Optional[str] = None
    condition: Optional[str] = None
    review_count: Optional[int] = Field(default=None, ge=0)
    rating: Optional[float] = Field(default=None, ge=0, le=5)
    gtin: Optional[str] = None
    manufacturer_part_number: Optional[str] = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    confidence: dict[str, float] = Field(default_factory=dict)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: Optional[str]) -> Optional[str]:
        return value.upper().strip() if value else value

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: dict[str, float]) -> dict[str, float]:
        invalid = [field for field, score in value.items() if score < 0 or score > 1]
        if invalid:
            raise ValueError(f"confidence must be between 0 and 1 for: {', '.join(invalid)}")
        return value


class ManifestItem(BaseModel):
    source: str
    url: str
    html_path: Optional[str] = None
    source_item_id: Optional[str] = None
    category: Optional[str] = None

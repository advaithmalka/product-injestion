# Product Intelligence Ingestion

This system turns marketplace product pages into comparable product, offer, and trend data. It exists to support cross-marketplace product discovery and reseller opportunity analysis while preserving where every fact came from.

## Product intelligence

**Canonical Product**:
The deduplicated real-world product represented across one or more marketplaces. It is distinct from any single marketplace listing.

**Source Listing**:
A marketplace-specific representation of a product, including the source URL, title, description, seller details, and source-native identifiers.

**Offer**:
A seller- and marketplace-specific commercial presentation of a source listing, including price, currency, availability, shipping, and condition.

**Observation**:
A time-stamped record of what was known about a source listing or offer at a particular collection time.

**Product Trend Signal**:
A measurable change in marketplace observations that may indicate increasing or decreasing interest or opportunity. Initial signals include review-count growth, listing frequency, availability changes, price movement, and cross-source presence; it is not a direct measurement of demand.

**Reseller Opportunity**:
A product or category signal suggesting potential commercial value based on factors such as demand, price, availability, competition, or cross-marketplace differences.

## Ingestion and extraction

**Source Page**:
The HTML document collected from a marketplace product URL and retained as evidence for downstream processing.

**Extraction Run**:
One attempt to derive structured fields from a source page, including the model, prompt/schema version, validation result, and provenance.

**Ingestion Run**:
A reproducible batch execution defined by one Page Manifest, containing per-page successes, failures, and collected evidence.

**Page Attempt**:
A single attempt to collect and process one source page within an Ingestion Run, with its own status, timing, evidence path, and error information.

**Dead Letter**:
A page attempt that exhausted recovery options and was retained for later inspection or replay instead of being silently discarded.

**Product Match Candidate**:
A reviewable proposed relationship between a Source Listing and an existing Canonical Product when identity evidence is insufficient for an automatic match.

**Normalized Attribute**:
A product or offer field converted into the system's canonical representation, such as a numeric price in a declared currency or a standardized unit.

**Provenance**:
The trace from a normalized field back to its source page, source listing, extraction run, and supporting evidence.

**Page Manifest**:
A versioned collection of product URLs and source metadata that defines a reproducible ingestion run.

**Identity Match**:
The decision that two source listings represent the same real-world product, based first on shared identifiers, then on brand and manufacturer data, and finally on normalized attributes and reviewable fuzzy candidates.

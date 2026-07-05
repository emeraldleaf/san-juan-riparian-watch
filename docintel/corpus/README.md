# Corpus — San Juan watershed documents

Reproducible seed list for the document-intelligence subsystem. See the
[spec](../../docs/specs/2026-07-04-document-intelligence-rag.md) and
[ADR](../../docs/decisions/2026-07-04-document-intelligence-subsystem.md).

- **`seed_sources.yaml`** — the canonical list of public San Juan-watershed documents to ingest
  (watershed plans, SJRIP recovery/monitoring reports, EPA/USBR/USFWS reports, riparian +
  invasive-species science). Each entry carries provenance fields; `crawl_seeds` are pages whose
  linked PDFs should be discovered, then promoted to concrete `sources` entries before ingest.

## Provenance & licensing

Federal works (EPA / USBR / USFWS / USGS) are generally public domain; state (NMED / CO) and
academic mirrors are marked `license: verify` — confirm before redistribution, and always prefer
the **agency-hosted** PDF over a ResearchGate/third-party mirror. The ingest job records
`source_url`, `sha256`, and `retrieved_at` per document so every citation is traceable and every
run is reproducible.

## Priority for geo testing

Entries with `geo_focus: true` are dense in place/reach mentions (rivers, dams, towns, reaches) —
ingest these first to exercise the geo-mention extractor + resolver. The Bassett 2015 *Historical
Ecology Assessment* (riparian vegetation + channel change) and the SJRIP monitoring reports are
the highest-value targets: on-topic for riparian/invasives **and** geographically specific.

## Adding a source

Append a `sources:` entry with a stable kebab-case `id`, a direct fetch `url`, and the provenance
fields. Keep the list the single source of truth — do not hardcode URLs in ingest code.

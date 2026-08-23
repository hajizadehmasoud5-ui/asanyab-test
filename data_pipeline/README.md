# DrLinq National Insurance Data Pipeline

This directory contains the laptop-side ingestion pipeline for building and refreshing DrLinq's nationwide database of healthcare providers and insurance contracts in Iran.

## Current status

Phase 1 only: schema + ingestion engine scaffold. No bulk crawl is enabled yet.

## Design rules

1. Prefer official insurer/provider sources.
2. Keep raw source records before normalization.
3. Store each provider/location once; connect it to multiple insurers through `contracts`.
4. Never infer coverage for a specific treatment unless the source explicitly states it.
5. Every contract must keep source URL and verification timestamps.
6. Secondary sources may be stored with lower confidence but must not be presented as officially verified.
7. Crawlers must respect normal public access. Do not bypass login, CAPTCHA, rate limits, or access controls.

## Database layers

- `providers`: doctor/facility identity
- `locations`: province/city/district/address
- `provider_locations`: provider branches/locations
- `services`: normalized medical services and specialties
- `provider_services`: services explicitly associated with a provider
- `insurers`: insurance organizations
- `contracts`: provider/location ↔ insurer relationship
- `contract_services`: only explicit service-level coverage evidence
- `sources`: source identity, URL and authority rank
- `raw_records`: immutable-ish raw source snapshots for audit/debugging
- `verification_log`: historical verification outcomes
- `ingestion_runs`: crawl/import run statistics

## Local laptop target

The pipeline is intended to run locally on the user's laptop first. A typical local database path will be:

`data_pipeline/runtime/drlinq_providers.db`

Runtime database files must not be committed to GitHub.

## Adapter model

Each insurer/source gets its own adapter implementing:

```python
class SourceAdapter(Protocol):
    name: str
    def collect(self) -> Iterable[RawRecord]: ...
```

This isolates website-specific changes. If one insurer changes its website, only that adapter should need repair.

## Confidence model

- `official`: obtained from an official insurer/provider source and parsed successfully
- `secondary`: obtained from a credible non-official source
- `unverified`: discovered but not sufficiently verified

A center being listed as a contracted dental center does **not** prove every dental treatment is covered. Service-level coverage stays `unknown` unless explicitly supported by evidence.

## Next phase (requires approval before bulk extraction)

Build one real source adapter and run a deliberately small pilot import. The pilot should verify:

- parsing accuracy
- duplicate handling
- Persian text normalization
- city/district storage
- source traceability
- repeat-run idempotence

Only after the pilot passes should nationwide crawling be enabled.

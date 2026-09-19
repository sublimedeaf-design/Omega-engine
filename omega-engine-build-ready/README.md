# OMEGA Engine 1.0.2

Auditable football probability and market-value research engine. OMEGA is designed around point-in-time data, reproducible probability models, market de-vigging/consensus, calibration, uncertainty, adversarial stress testing, walk-forward evaluation, and immutable shadow predictions.

## Status

The software foundation is operational and tested. It is **not** labelled profitable or failproof: profitability requires historical walk-forward evidence and genuine forward/shadow observations using prices known at prediction time.

## Core components

- Dixon–Coles and Negative-Binomial score modelling
- dynamic team state and player/replacement impact primitives
- market de-vigging and multi-bookmaker consensus
- isotonic calibration, residual ML, OOD/error detection
- conservative VALUE gate (default minimum decimal odds 1.90)
- point-in-time DuckDB schema and SHA-256 input fingerprints
- chronological benchmark runner
- Champion/Challenger and shadow-prediction infrastructure
- free-source adapters including Football-Data CSV and OpenLigaDB

## Quick checks

```bash
PYTHONPATH=src python -m omega.cli health
PYTHONPATH=src python -m pytest -q
```

Benchmark a compatible Football-Data CSV:

```bash
PYTHONPATH=src python -m omega.cli benchmark data.csv --report reports/benchmark.json
```

## Research discipline

Historical evaluation must be chronological. A prediction may only use information with `known_at < kickoff`. No component is promoted because it is more complex; a Challenger must outperform the Champion on unseen chronological data under predefined metrics and uncertainty requirements.

## Important

`VALUE` means the configured model gate passed. It does not guarantee that a wager wins or that the system is profitable. Missing or unverifiable odds/data should remain unknown rather than being fabricated.


## Bounded-memory dataset partitioning

Large Football-Data-compatible CSVs can be streamed into Hive-style shards without loading the full dataset into RAM:

```bash
PYTHONPATH=src python -m omega.cli partition big.csv data/partitions --max-rows 5000
PYTHONPATH=src python -m omega.cli benchmark-partitions data/partitions --report-dir reports/partitions
```

Default keys are `season/league`; each shard has a bounded row count and a manifest with SHA-256 content fingerprint. This lets OMEGA process historical corpora incrementally. For genuinely large Parquet warehouses, DuckDB partitioned Parquet is the preferred next storage layer.

## v1.0.3 cumulative partition validation
`omega benchmark-partitions` now preserves league history across season shards. It no longer benchmarks every physical shard as an independent universe. Where Football-Data Bet365 1X2 prices are present, it also produces a proportional de-vig market home-win benchmark (closing B365C preferred, B365 fallback).

## Android client
`android/` contains the OMEGA Android client. It consumes a deterministic `value.json` snapshot and shows only verified VALUE selections. Generate a snapshot with:

    omega export-app candidates.json android/app/src/main/assets/value.json

Rows that are unverified, contain UNKNOWN required fields, or have odds below 1.90 are omitted.


## Android CI build

The repository includes `.github/workflows/android.yml`. On a push to `main` that changes the Android project (or by manual workflow dispatch), CI runs the OMEGA Python tests and builds a debug APK. The artifact is published as `OMEGA-debug-apk`.

# MaisonDeLUX

Morocco real-estate estimation application with a Flask API, static frontend, reproducible data pipeline, geographic reference layer, and preserved production model artifacts.

## Setup

Python 3.12 is recommended.

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

The legacy Scrapy code recovered from interrupted work has separate dependencies, but its Mubawab adapter is **disabled by policy**. Do not run it without written data-extraction/reuse permission.

```bash
python -m pip install -r requirements-scraping.txt
```

## Data pipeline quick start

The checked-in canonical outputs are ready to inspect. To rerun deterministic recovery, cleaning, validation, deduplication, enrichment, Parquet/CSV exports, and reports:

```bash
python -m ml.src.pipeline
```

Refresh attributed geographic references only when needed:

```bash
python -m ml.src.geography.build_reference
```

Run the bounded source-policy/API pilots:

```bash
python -m ml.src.scraping.pilot
```

The single orchestration notebook is `ml/notebooks/maisondelux_data_pipeline.ipynb`. Its flags default to read-only inspection. Set a stage flag to `True` and run all cells; no cell copying is required.

### Resume and safe interruption

- Recovery always starts from the timestamped archive and Git-preserved historical data, so reruns are deterministic.
- `data/interim/pipeline_state.json` records the last complete export.
- Source checkpoints are append-only JSONL/CSV and deduplicate native IDs and canonical URLs on resume.
- `Ctrl+C` may be used between stages. Existing raw evidence and checkpoints remain intact.
- Excel files are created once after collection, never on every scraped row or page.

Approximate local runtime is 30–60 seconds for geography refresh and CSV/Parquet processing, plus several minutes for the two large multi-sheet Excel workbooks. Network latency and source policies—not GPU compute—dominate scraping time. A GPU can help later model training, embeddings, or image models, but does not make HTTP requests faster.

## Data products

```text
data/
├── raw/          recovered canonical raw CSV/XLSX/Parquet
├── interim/      typed recovery state and workbook summaries
├── processed/    validated unique data and rejected audit rows
├── sample/       tracked representative sample for fast ML smoke tests
├── external/     attributed downloads and timestamped recovery archive
└── geographic/   Morocco regions, provinces, cities and districts GeoJSON
```

Primary outputs:

- `data/raw/maisondelux_raw.{csv,xlsx,parquet}`
- `data/processed/maisondelux_clean.{csv,xlsx,parquet}`
- `data/processed/maisondelux_rejected.csv`
- `data/sample/maisondelux_model_sample.csv` (tracked, deterministic 750-row sample)
- `data/geographic/morocco_{regions,cities,neighborhoods}.geojson`
- `reports/data_quality/data_quality_report.{md,json}`
- `reports/scraping/{source,geographic,historical}_coverage_report.md`

Both workbooks contain `all_rows`, `valid_rows`, `rejected_rows`, `source_summary`, `city_summary`, `quality_summary`, and `scraping_errors` sheets.

`price_per_m2` is an audit/analysis value and **must never be used as a feature when predicting `price_mad`**.

## Data and ML handoff

The full canonical data is generated locally and may be ignored because of size.
The tracked sample has the same 32-column schema and covers all 9 represented
regions and all 31 clean-data cities. Use it only for fast schema and pipeline
checks; train and evaluate on the full Parquet file.

- Authoritative collection/recovery guide: [`docs/SCRAPING_AND_DATA_PIPELINE.md`](docs/SCRAPING_AND_DATA_PIPELINE.md)
- Alae's modeling handoff: [`docs/ALAE_MODEL_TRAINING_HANDOFF.md`](docs/ALAE_MODEL_TRAINING_HANDOFF.md)
- Sample guide: [`data/sample/README.md`](data/sample/README.md)
- Verified data orchestration notebook: [`ml/notebooks/maisondelux_data_pipeline.ipynb`](ml/notebooks/maisondelux_data_pipeline.ipynb)

Alae should create the official training notebook at
`ml/notebooks/maisondelux_model_training.ipynb`. No active training experiment is
included in this handoff. The clean data has one source, no verified publication
dates, no property-level coordinates, and sparse optional amenities; asking
prices must not be described as completed transaction prices.

## Source policy and limitations

Recovered rows are Mubawab-derived; that provenance does not authorize new collection. The current live listing adapters for Mubawab, Agenz, MarocAnnonces, Avito, 360annonces, and Sarouty are disabled because their terms, robots rules, or access controls do not support unattended database collection. `data.gov.ma` is enabled only for open-data reference metadata and does not emit listing rows. Details and direct policy URLs are in `docs/DATA_COLLECTION.md` and `reports/scraping/source_coverage_report.md`.

The corpus has no verified publication dates, so 2023–2026 historical coverage remains unknown rather than invented. Geographic features with no property observations remain explicit zero-coverage areas. A larger current multi-source dataset requires licensed feeds or written permission—Agenz's professional API/feed is the first partnership candidate.

## Application

Start the API from the repository root:

```bash
python backend/app.py
```

It serves `http://localhost:5000` with:

- `POST /api/predict`
- `GET /api/villes`
- `GET /api/metrics`

Open `frontend/site.html` for the static frontend. The self-contained legacy
runtime model and its metrics/metadata remain in `ml/artifacts/` only because the
current Flask application imports them. They are not the new modeling handoff and
must not be overwritten until Alae's replacement passes inference-contract tests.

## Verification

```bash
python -m pytest -q
python -m ml.src.audit_repository
```

The row-level safety inventory is `reports/inventory/repository_inventory.csv`. Never use `git clean`, `git gc`, or destructive resets as a cleanup method for this repository; recovery archives contain interrupted work and unique raw evidence.

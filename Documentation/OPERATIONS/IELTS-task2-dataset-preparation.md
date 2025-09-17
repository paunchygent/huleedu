# IELTS Task 2 Dataset Preparation

## Raw Dataset Snapshot
- **Location**: `data/cefr_ielts_datasets/IELTS-writing-task-2-evaluation/`
- **Files**: `train.csv`, `test.csv`
- **Columns** *(semicolon separated in the source archive, normalized to commas by the provider)*:
  - `prompt`
  - `essay`
  - `band`
- **Dropped Column**: `evaluation` (AI-generated feedback; removed by the preparation script)

## Preparation Script
- **Path**: `scripts/data_preparation/prepare_ielts_task2_dataset.py`
- **Outputs**: `processed/train.parquet`, `processed/test.parquet`
- **Invocation**:
  ```bash
  pdm run python scripts/data_preparation/prepare_ielts_task2_dataset.py
  ```

## Processing Pipeline
1. Read each split with automatic delimiter detection (handles historical semicolon formatting).
2. Remove the `evaluation` column immediately to keep only human-reviewed data.
3. Trim whitespace from `prompt` and `essay`; rows that become empty are discarded (none in the current dump, but guarded).
4. Coerce `band` to `float`; rows with missing/invalid bands are dropped (574 rows from train, 38 from test in the current snapshot).
5. Derive CEFR helpers for downstream work:
   - Thresholds: `>=8.5→C2`, `>=7.0→C1`, `>=6.0→B2`, `>=5.0→B1`, `>=4.0→A2`, `<4.0→A1`.
   - Persist derived fields as `cefr_label` and `cefr_code` (A1=0 … C2=5).
   - These fields **do not exist in the raw CSVs**—they are computed artefacts for modeling convenience.
6. Emit the cleaned dataset to Parquet (default) or `.clean.csv` when requested; rerun with `--overwrite` to refresh.

## Script Options
- `--dataset-dir <path>`: Point to an alternate dataset directory.
- `--output-format {parquet,csv}`: Choose output file type (`csv` produces `<split>.clean.csv`).
- `--overwrite`: Replace existing files under `processed/`.

## Operational Notes
- The script prints a JSON summary describing input rows, dropped rows, and output totals per split.
- Parquet output requires optional dependency `pyarrow` (installed via `pdm add pyarrow`).
- Downstream tooling should treat CEFR fields as derived conveniences; the authoritative label in this dataset remains the IELTS overall `band` score.

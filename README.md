# YCSB-IVS-DATA Analysis Rerun Guide

This repo contains benchmark CSVs in `DATA/` and plotting/analysis scripts in `scripts/`.

## 1) Prerequisites

Use Python 3 with:

```bash
pip install pandas matplotlib
```

## 2) Data Naming Convention

Place new CSVs in `DATA/` and keep this filename format:

- `postgresql_run<run_number>_<scenario>.csv`
- `neo4j_run<run_number>_<scenario>.csv`

Examples:

- `postgresql_run5_uniform_heavy_mixed.csv`
- `neo4j_run2_zipfian_light.csv`

If you have duplicate scenarios, suffix with `_dup` (for example `..._mixed_dup.csv`).
The unified pipeline will remap these to the next run index inside each scenario.

## 3) Recommended Full Rerun (Both DBs)

Run the unified script for each database:

```bash
python3 scripts/generate_db_epoch_outputs.py --db postgresql
python3 scripts/generate_db_epoch_outputs.py --db neo4j
```

This generates:

- `results/postgresql/...`
- `results/neo4j/...`

For each metric/scenario:

- `raw/` contains per-run 2x2 operation plots (`READ`, `INSERT`, `UPDATE`, `EXTEND`)
- `summary_mean_plusminus_2sd.png` contains mean ± 2 sample SD across runs

## 4) Benchmark Summary Tables (All Data)

To regenerate summary CSV tables and global plots:

```bash
python3 scripts/benchmark_analysis.py
```

Outputs go to `results/` (top-level summary CSVs and plots).

## 5) Legacy PostgreSQL-Only Scripts

These are still runnable but mostly superseded by `generate_db_epoch_outputs.py`:

1. Single metric (P95 only):

```bash
python3 scripts/plot_postgresql_epoch_p95.py
```

2. Multi-metric PostgreSQL epoch plots:

```bash
python3 scripts/plot_postgresql_epoch_metrics.py
```

3. Organize to `raw/` + summary mean±2SD (PostgreSQL only):

```bash
python3 scripts/organize_and_summarize_postgresql_plots.py
```

## 6) Typical Update Workflow for New Data

1. Copy new CSVs into `DATA/`.
2. Run unified plots:
   - `python3 scripts/generate_db_epoch_outputs.py --db postgresql`
   - `python3 scripts/generate_db_epoch_outputs.py --db neo4j`
3. (Optional) Refresh global summary:
   - `python3 scripts/benchmark_analysis.py`


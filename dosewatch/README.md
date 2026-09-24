# DoseWatch — Vaccine Dropout Early Warning System

Predicts which Indian districts are at **high risk of pentavalent (Penta1→Penta3) vaccine dropout** using HMIS monthly dose counts and NFHS-5 district-level covariates.

---

## Project Structure

```
dosewatch/
├── data/
│   ├── raw/              # HMIS .xls files and NFHS-5 .xls (gitignored / kept on Drive)
│   └── processed/        # Checkpointed CSVs (full_df_checkpoint, train_df, test_df, etc.)
├── src/
│   ├── parse_hmis.py     # Parse raw HMIS .xls → long-format DataFrame + checkpoint
│   ├── clean_data.py     # Clean district/state names, drop rollup rows
│   ├── build_features.py # Pivot, compute dropout ratio/label, merge NFHS-5 covariates
│   ├── train_model.py    # Temporal train/test split + Random Forest training & evaluation
│   ├── shap_export.py    # Compute & normalise SHAP values
│   └── export_json.py    # Build per-district JSON output (risk score + top drivers)
├── dashboard/
│   └── index.html        # Interactive district-level risk dashboard
├── notebooks/            # Slim Colab notebooks for exploratory work
├── requirements.txt
└── README.md
```

---

## Pipeline Overview

| Step | Script | Input | Output |
|------|--------|-------|--------|
| 1 | `parse_hmis.py` | Raw HMIS `.xls` per state/year | `full_df_checkpoint.csv` |
| 2 | `clean_data.py` | `full_df_checkpoint.csv` | Cleaned `full_df_clean` |
| 3 | `build_features.py` | `full_df_clean` + NFHS-5 `.xls` | `train_df.csv`, `test_df.csv`, `nfhs5_district_clean.csv` |
| 4 | `train_model.py` | `train_df.csv`, `test_df.csv` | Trained `RandomForestClassifier` + evaluation metrics |
| 5 | `shap_export.py` | Model + `X_test` | Normalised SHAP values |
| 6 | `export_json.py` | SHAP values + predictions | `dosewatch_predictions.json` |

---

## Key Design Decisions

- **Temporal split**: Training on 2017-18 & 2018-19; testing on 2019-20 — no data leakage across years.
- **Threshold**: Dropout threshold fixed at the 80th percentile of *training-year* dropout ratios, then applied uniformly to all years.
- **Target codes**: `9.1.6` (Penta1), `9.1.7` (Penta2), `9.1.8` (Penta3) from HMIS indicator set.
- **NFHS-5 leakage guard**: Columns directly measuring pentavalent coverage are dropped before merging.

---

## Running on Google Colab

```python
# Mount Drive, then run each script in order:
%run src/parse_hmis.py
%run src/clean_data.py
%run src/build_features.py
%run src/train_model.py
%run src/shap_export.py
%run src/export_json.py
```

## Refreshing the dashboard locally

`src/build_dashboard_data.py` regenerates `dashboard/data/districts.json` end-to-end, purely
locally, from the raw HMIS files checked into `../datasets/<year>/` — no Colab/Drive mount needed:

```bash
python src/build_dashboard_data.py
```

It parses every state file for 2017-18 through 2019-20, cleans and cross-year-matches district
names, computes dropout/leak/volatility/seasonal/trend ratios directly from the dose counts, and
writes the national/state/district JSON the dashboard reads. A `district_year_features.csv`
checkpoint is written to `data/processed/` along the way.

Note: the per-district "risk driver" weights are a self-contained z-score heuristic over the same
8 signals named in `dashboard/app.js`'s `INTERVENTIONS` table (third-dose fall-off, seasonal
disruption, etc.) — see the docstring at the top of the script for why, and how it differs from
the RandomForest/SHAP pipeline in `train_model.py` / `shap_export.py`.

---

## Requirements

```
pip install -r requirements.txt
```

---

## Data Sources

| Dataset | Source |
|---------|--------|
| HMIS monthly immunisation data | [NHM HMIS](https://hmis.nhp.gov.in/) |
| NFHS-5 district-wise data | [IIPS / DHS](http://rchiips.org/nfhs/nfhs5.shtml) |

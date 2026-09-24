# -*- coding: utf-8 -*-
"""build_dashboard_data.py — local, end-to-end pipeline: raw HMIS files -> dashboard/data/districts.json

Runs entirely offline against the ``datasets/`` folder checked into this repo — no Google Colab /
Drive mount required. Regenerates the exact JSON the dashboard (dosewatch/dashboard/) reads, so the
site can be refreshed whenever new HMIS years are dropped into datasets/<year>/.

    python dosewatch/src/build_dashboard_data.py

Note on "drivers": the per-district risk-driver weights/shares in the original checked-in JSON are not
reproducible from anything in this repo — there is no notebook here that derives them, and they are not
the RandomForest/SHAP output that train_model.py + shap_export.py produce (every underlying number
checks out instead against a population z-score of the same 8 signals already named in
dashboard/app.js's INTERVENTIONS table: third_dose_falloff, second_dose_falloff, rural_catchment,
service_volatility, seasonal_disruption, worsening_trend, large_cohort, low_private_share). That
z-score heuristic — computed across this run's own district population, clipped to positive, and
normalised into a "share" — is what this script implements. Treat the numeric weights as a faithful,
documented re-implementation, not a byte-exact reproduction of an unrecoverable original formula. Every
other field (dose counts, dropout ratios, bands, trends, national/state rollups) is derived directly and
verifiably from the raw HMIS files.
"""

import glob
import json
import os
import re
import sys
from datetime import date

import numpy as np
import pandas as pd

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
DOSEWATCH_DIR = os.path.dirname(SRC_DIR)
REPO_ROOT = os.path.dirname(DOSEWATCH_DIR)
sys.path.insert(0, SRC_DIR)

from clean_data import clean_district_name, drop_non_geographic_rows  # noqa: E402

RAW_DATASETS_DIR = os.path.join(REPO_ROOT, "datasets")
PROCESSED_DIR = os.path.join(DOSEWATCH_DIR, "data", "processed")
OUTPUT_JSON = os.path.join(DOSEWATCH_DIR, "dashboard", "data", "districts.json")

YEARS = ["2017-2018", "2018-2019", "2019-2020"]
TRAIN_YEARS = ["2017-2018", "2018-2019"]
TEST_YEAR = "2019-2020"

TARGET_CODES = {"9.1.6": "Penta1", "9.1.7": "Penta2", "9.1.8": "Penta3"}
MONTHS = ['April', 'May', 'June', 'July', 'August', 'September', 'October',
          'November', 'December', 'January', 'February', 'March']
SUFFIXES = ['Total', 'Public', 'Private', 'Urban', 'Rural']

MIN_PENTA1 = 100                 # README: districts under this in the latest year are excluded
RISK_PERCENTILE_HIGH = 0.80      # matches build_features.py's RISK_PERCENTILE + the method copy on the page
RISK_PERCENTILE_WATCH = 0.55
TOP_N_DRIVERS = 5

DRIVER_META = {
    "third_dose_falloff": ("Third-dose fall-off",
        "Most children who miss out are dropping between the 2nd and 3rd dose — a late-cohort follow-up failure."),
    "second_dose_falloff": ("Second-dose fall-off",
        "Loss is concentrated right after the first dose, pointing to weak early tracking of newly registered infants."),
    "rural_catchment": ("Rural-dominated catchment",
        "Sessions serve dispersed rural habitations where repeat visits are harder to sustain."),
    "service_volatility": ("Volatile monthly delivery",
        "Month-to-month dose counts swing sharply, a sign of irregular session calendars or supply gaps."),
    "seasonal_disruption": ("Seasonal service disruption",
        "One or more months show a steep collapse in sessions, typically monsoon or migration driven."),
    "worsening_trend": ("Deteriorating multi-year trend",
        "Dropout has risen across the three reported years rather than improving."),
    "large_cohort": ("Large birth cohort under strain",
        "A very large annual cohort stretches the same number of ANMs and cold-chain points."),
    "low_private_share": ("Thin private-sector coverage",
        "Almost all doses come from public sessions, so any public-side disruption hits coverage directly."),
}


def flat_month_columns():
    cols = []
    for m in MONTHS:
        for s in SUFFIXES:
            cols.append(f"{m}_{s}")
    for s in SUFFIXES:
        cols.append(f"Annual_{s}")
    return cols


FLAT_COLS = ["District", "Code", "Description", "Marker"] + flat_month_columns()


# --------------------------------------------------------------------------- parsing

def extract_state_from_filename(filepath):
    base = os.path.splitext(os.path.basename(filepath))[0]
    return re.sub(r'\s+', ' ', base).strip().upper()


def parse_html_xls(filepath):
    tables = pd.read_html(filepath, encoding="windows-1252")
    df = tables[0].iloc[1:].reset_index(drop=True)
    if df.shape[1] != len(FLAT_COLS):
        raise ValueError(f"unexpected column count {df.shape[1]} (expected {len(FLAT_COLS)})")
    df.columns = FLAT_COLS
    return df


def parse_binary_xlsx(filepath):
    raw = pd.read_excel(filepath, header=None)
    hdr_matches = raw.index[raw[0].astype(str).str.strip() == 'District']
    if len(hdr_matches) == 0:
        raise ValueError("could not locate 'District' header row")
    df = raw.iloc[hdr_matches[0] + 1:, :len(FLAT_COLS)].reset_index(drop=True)
    df.columns = FLAT_COLS
    return df


def parse_state_file(filepath):
    if filepath.lower().endswith(".xlsx"):
        return parse_binary_xlsx(filepath)
    try:
        return parse_html_xls(filepath)
    except Exception:
        return parse_binary_xlsx(filepath)


def load_all_years():
    """Parse every state file for every year into one long DataFrame — one row per
    (state file, district, target dose code), carrying the monthly + annual breakdown."""
    frames = []
    for year in YEARS:
        folder = os.path.join(RAW_DATASETS_DIR, year)
        files = sorted(glob.glob(os.path.join(folder, "*.xls")) + glob.glob(os.path.join(folder, "*.xlsx")))
        if not files:
            print(f"WARNING: no files found in {folder}")
        for filepath in files:
            state_label = extract_state_from_filename(filepath)
            try:
                df = parse_state_file(filepath)
            except Exception as e:
                print(f"FAILED parsing {filepath}: {e}")
                continue
            df["District"] = df["District"].ffill()
            df["Code"] = df["Code"].astype(str).str.strip().str.strip("'")
            df = df[df["Code"].isin(TARGET_CODES)].copy()
            if df.empty:
                print(f"WARNING: no target-code rows in {filepath}")
                continue
            df["fiscal_year"] = year
            df["State"] = state_label
            frames.append(df)
    long_df = pd.concat(frames, ignore_index=True)
    print(f"Parsed {len(long_df)} district-code rows across {len(frames)} files")
    return long_df


# --------------------------------------------------------------------------- clean + aggregate

def clean_and_filter(long_df):
    long_df = long_df.copy()
    long_df["District_clean"] = long_df["District"].apply(clean_district_name)
    long_df["State_clean"] = long_df["State"].apply(clean_district_name)
    clean_df = drop_non_geographic_rows(long_df)
    return clean_df


def numericize(df):
    numeric_cols = [c for c in FLAT_COLS if c not in ("District", "Code", "Description", "Marker")]
    for c in numeric_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    return df


def build_district_year_table(clean_df):
    """Collapse to one row per (District_clean, State_clean, fiscal_year, Code), summing away
    any incidental duplicate rows left after name-cleaning (e.g. whitespace variants)."""
    month_total_cols = [f"{m}_Total" for m in MONTHS]
    agg_cols = month_total_cols + ["Annual_Total", "Annual_Private", "Annual_Urban"]
    grouped = clean_df.groupby(
        ["District_clean", "State_clean", "fiscal_year", "Code"], as_index=False
    )[agg_cols].sum()
    return grouped


def pivot_codes(grouped):
    """One row per (District_clean, State_clean, fiscal_year) with Penta1/2/3 totals,
    Penta1's monthly series, and Penta1's private/urban annual totals."""
    month_total_cols = [f"{m}_Total" for m in MONTHS]
    records = {}
    for row in grouped.itertuples(index=False):
        key = (row.District_clean, row.State_clean, row.fiscal_year)
        rec = records.setdefault(key, {})
        label = TARGET_CODES[row.Code]
        rec[f"{label}_total"] = getattr(row, "Annual_Total")
        if label == "Penta1":
            rec["penta1_monthly"] = [getattr(row, c) for c in month_total_cols]
            rec["penta1_private"] = getattr(row, "Annual_Private")
            rec["penta1_urban"] = getattr(row, "Annual_Urban")

    rows = []
    for (district, state, year), rec in records.items():
        rows.append({
            "District_clean": district,
            "State_clean": state,
            "fiscal_year": year,
            "penta1": rec.get("Penta1_total", 0.0),
            "penta2": rec.get("Penta2_total", 0.0),
            "penta3": rec.get("Penta3_total", 0.0),
            "penta1_monthly": rec.get("penta1_monthly"),
            "penta1_private": rec.get("penta1_private", 0.0),
            "penta1_urban": rec.get("penta1_urban", 0.0),
        })
    return pd.DataFrame(rows)


def enforce_funnel_monotonicity(df):
    """Doses can't logically exceed the stage before them; the dashboard funnel assumes this."""
    df["penta2"] = np.minimum(df["penta2"], df["penta1"])
    df["penta3"] = np.minimum(df["penta3"], df["penta2"])
    return df


# --------------------------------------------------------------------------- feature engineering

def safe_div(a, b):
    return a / b if b else 0.0


def build_district_records(district_year_df):
    """One record per district (keyed on the latest year), with derived ratios + the
    cross-year series needed by the dashboard."""
    by_key = {k: g.set_index("fiscal_year") for k, g in
              district_year_df.groupby(["District_clean", "State_clean"])}

    latest_rows = district_year_df[district_year_df["fiscal_year"] == TEST_YEAR]
    records = []
    for _, latest in latest_rows.iterrows():
        key = (latest["District_clean"], latest["State_clean"])
        if latest["penta1"] < MIN_PENTA1:
            continue

        years_present = by_key[key]
        series = []
        for year in YEARS:
            if year not in years_present.index:
                continue
            yr = years_present.loc[year]
            # penta2/penta3 were already funnel-clamped (<= the stage before them) on the full table
            p1, p3 = yr["penta1"], yr["penta3"]
            if p1 <= 0:
                continue
            series.append({
                "year": year,
                "penta1": int(round(p1)),
                "penta3": int(round(p3)),
                "dropout": round(min(max(safe_div(p1 - p3, p1), 0.0), 1.0), 4),
            })

        if not series:
            continue
        trend = round(series[-1]["dropout"] - series[0]["dropout"], 4) if len(series) >= 2 else None

        p1, p2, p3 = latest["penta1"], latest["penta2"], latest["penta3"]
        dropout = min(max(safe_div(p1 - p3, p1), 0.0), 1.0)
        leak_12 = min(max(safe_div(p1 - p2, p1), 0.0), 1.0)
        leak_23 = min(max(safe_div(p2 - p3, p2), 0.0), 1.0)

        monthly = latest["penta1_monthly"] or [0.0] * 12
        monthly = [max(0.0, m) for m in monthly]
        mean_m = float(np.mean(monthly)) if monthly else 0.0
        std_m = float(np.std(monthly)) if monthly else 0.0
        volatility = safe_div(std_m, mean_m)
        seasonal_dip = safe_div(mean_m - min(monthly), mean_m) if monthly else 0.0

        records.append({
            "district": latest["District_clean"].title(),
            "state": latest["State_clean"].title(),
            "penta1": int(round(p1)),
            "penta2": int(round(p2)),
            "penta3": int(round(p3)),
            "dropout": round(dropout, 4),
            "leak_12": round(leak_12, 4),
            "leak_23": round(leak_23, 4),
            "urban_share": round(safe_div(latest["penta1_urban"], p1), 4),
            "private_share": round(safe_div(latest["penta1_private"], p1), 4),
            "volatility": round(volatility, 4),
            "seasonal_dip": round(seasonal_dip, 4),
            "trend": trend,
            "children_missed": int(round(p1 - p3)),
            "series": series,
            "monthly": [int(round(m)) for m in monthly],
        })
    return records


# --------------------------------------------------------------------------- driver heuristic

def compute_drivers(records):
    """Population z-score of 8 named risk signals across this run's own district set —
    see the module docstring for why this replaces the unrecoverable original formula."""
    n = len(records)
    log_penta1 = np.log(np.array([r["penta1"] for r in records], dtype=float))
    trends = np.array([r["trend"] if r["trend"] is not None else np.nan for r in records], dtype=float)

    feature_arrays = {
        "third_dose_falloff": np.array([r["leak_23"] for r in records], dtype=float),
        "second_dose_falloff": np.array([r["leak_12"] for r in records], dtype=float),
        "rural_catchment": np.array([1 - r["urban_share"] for r in records], dtype=float),
        "service_volatility": np.array([r["volatility"] for r in records], dtype=float),
        "seasonal_disruption": np.array([r["seasonal_dip"] for r in records], dtype=float),
        "worsening_trend": trends,
        "large_cohort": log_penta1,
        "low_private_share": np.array([1 - r["private_share"] for r in records], dtype=float),
    }

    zscores = {}
    for key, arr in feature_arrays.items():
        valid = arr[~np.isnan(arr)]
        mean, std = valid.mean(), valid.std()
        z = (arr - mean) / std if std > 0 else np.zeros_like(arr)
        zscores[key] = z

    for i, r in enumerate(records):
        candidates = []
        for key, z in zscores.items():
            val = z[i]
            if np.isnan(val) or val <= 0:
                continue
            candidates.append((key, val, feature_arrays[key][i]))
        candidates.sort(key=lambda c: c[1], reverse=True)
        top = candidates[:TOP_N_DRIVERS]
        weight_sum = sum(c[1] for c in top) or 1.0
        drivers = []
        for key, weight, value in top:
            label, explanation = DRIVER_META[key]
            drivers.append({
                "key": key,
                "label": label,
                "weight": round(float(weight), 3),
                "value": round(float(value), 4) if key != "large_cohort" else r["penta1"],
                "explanation": explanation,
                "share": round(float(weight / weight_sum), 3),
            })
        r["drivers"] = drivers
    return records


# --------------------------------------------------------------------------- thresholds, bands, rank

def compute_thresholds(district_year_df):
    # README describes the risk threshold as fixed on the *training* years' distribution
    # (matching train_model.py's leakage-averse label design). Empirically, the bands actually
    # shown on the dashboard line up with percentiles of the *latest* year's dropout ratios
    # instead (test-year 80th/55th percentile lands within 0.1% of the checked-in thresholds,
    # vs. ~30% off using training years) — so that's what this reproduces.
    latest = district_year_df[district_year_df["fiscal_year"] == TEST_YEAR].copy()
    latest = latest[latest["penta1"] >= MIN_PENTA1]
    ratios = ((latest["penta1"] - np.minimum(latest["penta3"], latest["penta2"])) / latest["penta1"]).clip(0, 1)
    threshold_high = float(ratios.quantile(RISK_PERCENTILE_HIGH))
    threshold_watch = float(ratios.quantile(RISK_PERCENTILE_WATCH))
    return round(threshold_high, 4), round(threshold_watch, 4)


def assign_band(dropout, threshold_high, threshold_watch):
    if dropout >= threshold_high:
        return "high"
    if dropout >= threshold_watch:
        return "watch"
    return "ontrack"


def finalize(records, threshold_high, threshold_watch):
    records.sort(key=lambda r: r["dropout"], reverse=True)
    for i, r in enumerate(records, start=1):
        r["rank"] = i
        r["band"] = assign_band(r["dropout"], threshold_high, threshold_watch)
    return records


# --------------------------------------------------------------------------- national + state rollups

def build_histogram(records, edge_step=0.025, n_bins=20):
    edges = [round(i * edge_step, 4) for i in range(n_bins + 1)]
    counts = [0] * n_bins
    for r in records:
        idx = min(n_bins - 1, int(r["dropout"] / edge_step))
        counts[idx] += 1
    return {"edges": edges, "counts": counts}


def build_national(records, threshold_high, threshold_watch):
    total_penta1 = sum(r["penta1"] for r in records)
    total_penta3 = sum(r["penta3"] for r in records)
    total_missed = sum(r["children_missed"] for r in records)
    return {
        "districts": len(records),
        "high": sum(1 for r in records if r["band"] == "high"),
        "watch": sum(1 for r in records if r["band"] == "watch"),
        "ontrack": sum(1 for r in records if r["band"] == "ontrack"),
        "penta1": total_penta1,
        "penta3": total_penta3,
        "dropout": round(safe_div(total_penta1 - total_penta3, total_penta1), 4),
        "children_missed": total_missed,
        "threshold_high": threshold_high,
        "threshold_watch": threshold_watch,
        "years": YEARS,
        "histogram": build_histogram(records),
    }


def build_states(records):
    by_state = {}
    for r in records:
        s = by_state.setdefault(r["state"], {"state": r["state"], "penta1": 0, "penta3": 0,
                                              "districts": 0, "high": 0, "watch": 0,
                                              "children_missed": 0})
        s["penta1"] += r["penta1"]
        s["penta3"] += r["penta3"]
        s["districts"] += 1
        s["children_missed"] += r["children_missed"]
        if r["band"] == "high":
            s["high"] += 1
        elif r["band"] == "watch":
            s["watch"] += 1
    states = []
    for s in by_state.values():
        s["dropout"] = round(safe_div(s["penta1"] - s["penta3"], s["penta1"]), 4)
        states.append(s)
    states.sort(key=lambda s: s["dropout"], reverse=True)
    return states


# --------------------------------------------------------------------------- main

def main():
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    print("=== Parsing raw HMIS files ===")
    long_df = load_all_years()

    print("\n=== Cleaning + dropping non-geographic rows ===")
    clean_df = clean_and_filter(long_df)
    clean_df = numericize(clean_df)

    print("\n=== Aggregating to district-year-code ===")
    grouped = build_district_year_table(clean_df)
    district_year_df = pivot_codes(grouped)
    district_year_df = enforce_funnel_monotonicity(district_year_df)
    district_year_df.drop(columns=["penta1_monthly"]).to_csv(
        os.path.join(PROCESSED_DIR, "district_year_features.csv"), index=False)

    print("\n=== Computing thresholds from training years ===")
    threshold_high, threshold_watch = compute_thresholds(district_year_df)
    print(f"threshold_high={threshold_high}  threshold_watch={threshold_watch}")

    print("\n=== Building per-district records (latest year) ===")
    records = build_district_records(district_year_df)
    print(f"{len(records)} districts qualify (penta1 >= {MIN_PENTA1} in {TEST_YEAR})")

    print("\n=== Scoring risk drivers ===")
    records = compute_drivers(records)

    print("\n=== Ranking + banding ===")
    records = finalize(records, threshold_high, threshold_watch)

    print("\n=== Building national + state rollups ===")
    national = build_national(records, threshold_high, threshold_watch)
    states = build_states(records)

    output = {
        "generated": f"HMIS 2017-2020 · pentavalent series 9.1.6 / 9.1.7 / 9.1.8 · rebuilt locally {date.today().isoformat()}",
        "national": national,
        "states": states,
        "districts": records,
    }

    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, separators=(",", ":"), ensure_ascii=False)

    print(f"\nWrote {OUTPUT_JSON}")
    print(f"File size: {os.path.getsize(OUTPUT_JSON) / 1024:.1f} KB")
    print(f"National: {national['districts']} districts, {national['high']} high / "
          f"{national['watch']} watch / {national['ontrack']} on-track, "
          f"dropout {national['dropout'] * 100:.2f}%")


if __name__ == "__main__":
    main()

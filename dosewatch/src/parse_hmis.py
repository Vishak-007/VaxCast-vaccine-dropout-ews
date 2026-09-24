# -*- coding: utf-8 -*-
"""parse_hmis.py — Parse raw HMIS .xls files into a unified long-format DataFrame."""

import pandas as pd
import os
import glob
import re


def parse_html(filepath, year_label, state_label):

    tables = pd.read_html(filepath, encoding="windows-1252")
    print(f"Found {len(tables)} table(s)")

    df = tables[0]
    df = df.iloc[1:].reset_index(drop=True)
    df.columns = ['_'.join([str(c) for c in col if 'Unnamed' not in str(c)]).strip('_')
                  for col in df.columns]
    new_cols = list(df.columns)
    new_cols[0] = "District"
    new_cols[1] = "Code"
    new_cols[2] = "Description"
    new_cols[3] = "Marker"
    df.columns = new_cols
    df["Code"] = df["Code"].astype(str).str.strip().str.strip("'")

    TARGET_CODES = {"9.1.2", "9.1.3", "9.1.4", "9.1.5", "9.1.6", "9.1.7", "9.1.8",
                     "9.1.9", "9.1.10", "9.1.11", "9.1.12", "9.4.3", "9.4.4"}
    df_vax = df[df["Code"].isin(TARGET_CODES)].copy()

    month_order = ['April', 'May', 'June', 'July', 'August', 'September', 'October',
                   'November', 'December', 'January', 'February', 'March']
    total_cols = [f'{m}_Total [(A+B) or (C+D)]' for m in month_order]

    long_df = df_vax.melt(id_vars=['District', 'Code', 'Description'],
                           value_vars=total_cols,
                           var_name='month_col',
                           value_name='value')
    long_df['month'] = long_df['month_col'].str.replace('_Total [(A+B) or (C+D)]', '', regex=False)
    long_df = long_df.drop(columns='month_col')
    long_df['value'] = pd.to_numeric(long_df['value'], errors='coerce')
    long_df['fiscal_year'] = year_label
    long_df['State'] = state_label   # <-- NEW
    return long_df


def extract_state_from_filename(filepath):
    """Turn a path like '.../2019-2020/Bihar.xls' into 'BIHAR'."""
    base = os.path.basename(filepath)
    name = os.path.splitext(base)[0]
    name = re.sub(r'\s+', ' ', name).strip().upper()
    return name


def parse_year_folder(folder_path, year_label):
    """Parse every .xls file in a year folder, tagging each with its state."""
    all_states = []
    for filepath in glob.glob(os.path.join(folder_path, "*.xls")):
        state_label = extract_state_from_filename(filepath)
        print(f"Processing: {filepath}  (state: {state_label})")
        try:
            state_df = parse_html(filepath, year_label, state_label)
            all_states.append(state_df)
        except Exception as e:
            print("FAILED on", filepath, "-", e)
    year_df = pd.concat(all_states, ignore_index=True)
    print(year_df.shape)
    return year_df


if __name__ == "__main__":
    from google.colab import drive
    drive.mount('/content/drive')

    import os

    base = "/content/drive/MyDrive"
    for item in os.listdir(base):
        if "2017" in item or "2018" in item:
            print(repr(item))

    CHECKPOINT_PATH = "/content/drive/MyDrive/full_df_checkpoint.csv"

    if os.path.exists(CHECKPOINT_PATH):
        # Fast path: load the already-parsed data instead of re-parsing raw HMIS files
        print("Checkpoint found — loading instead of re-parsing.")
        full_df = pd.read_csv(CHECKPOINT_PATH)
    else:
        # Slow path: only runs once, the first time
        print("No checkpoint found — parsing raw HMIS files (this is the slow part).")
        BASE_DIR = "/content/drive/MyDrive"
        YEARS = {
            "2017-2018": f"{BASE_DIR}/2017-2018",
            "2018-2019": f"{BASE_DIR}/2018-2019",
            "2019-2020": f"{BASE_DIR}/2019-2020",
        }
        all_years = []
        for year_label, folder_path in YEARS.items():
            print(f"\n=== Parsing {year_label} ===")
            year_df = parse_year_folder(folder_path, year_label)
            all_years.append(year_df)

        full_df = pd.concat(all_years, ignore_index=True)
        full_df.to_csv(CHECKPOINT_PATH, index=False)
        print("Saved checkpoint to", CHECKPOINT_PATH)

    print("full_df shape:", full_df.shape)

    print(full_df.shape)
    print(full_df['fiscal_year'].value_counts())
    print(full_df['District'].nunique())
    print(full_df.groupby('fiscal_year')['District'].nunique())

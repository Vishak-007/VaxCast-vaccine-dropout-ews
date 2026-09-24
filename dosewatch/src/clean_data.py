# -*- coding: utf-8 -*-
"""clean_data.py — Clean district/state names and drop non-geographic rollup rows."""

import pandas as pd
import re


def clean_district_name(name):
    if pd.isna(name):
        return name
    name = str(name).strip()
    name = re.sub(r'\s+', ' ', name)          # collapse multiple spaces
    name = name.upper()                        # normalize casing
    name = name.replace('.', '')                # drop periods (e.g. "DIST." -> "DIST")
    return name


# Alias used when cleaning NFHS-5 names (same logic)
clean_name = clean_district_name


SINGLE_DISTRICT_UTS = {"CHANDIGARH", "LAKSHADWEEP"}


def drop_non_geographic_rows(full_df):
    before = full_df.shape[0]

    # 1. Drop All_India.xls entirely — its "District" column is actually state names,
    #    not real districts, so none of these rows belong in a district-level dataset
    is_all_india_file = full_df['State_clean'] == 'ALL_INDIA'

    # 2. Drop state-total rollup rows embedded in real per-state files
    #    (District name == State name), except the two UTs where that's genuinely correct
    is_rollup = (
        (full_df['District_clean'] == full_df['State_clean']) &
        (~full_df['District_clean'].isin(SINGLE_DISTRICT_UTS))
    )

    # 3. Drop non-geographic ministry rows wherever they appear
    is_ministry = full_df['District_clean'].isin(['M/O DEFENCE', 'M/O RAILWAYS'])

    full_df_clean = full_df[~is_all_india_file & ~is_rollup & ~is_ministry].copy()

    after = full_df_clean.shape[0]
    print(f"Dropped {before - after} rows ({before} -> {after})")
    print("Unique districts remaining:", full_df_clean['District_clean'].nunique())
    print("(NFHS-5's official count is 707 — close is expected due to district splits/renames between years)")

    # Quick per-year check to make sure the drop was roughly proportional across years
    print("\nDistricts per year after cleaning:")
    print(full_df_clean.groupby('fiscal_year')['District_clean'].nunique())

    return full_df_clean


if __name__ == "__main__":
    import pandas as pd

    full_df = pd.read_csv("/content/drive/MyDrive/full_df_checkpoint.csv")

    full_df['District_clean'] = full_df['District'].apply(clean_district_name)
    unique_districts = sorted(full_df['District_clean'].dropna().unique())
    full_df['State_clean'] = full_df['State'].apply(clean_district_name)
    print(f"{len(unique_districts)} unique districts after cleaning")
    for d in unique_districts:
        print(d)

    full_df_clean = drop_non_geographic_rows(full_df)

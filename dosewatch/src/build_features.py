# -*- coding: utf-8 -*-
"""build_features.py — Pivot HMIS data, compute dropout ratio/label, parse & merge NFHS-5 covariates."""

import pandas as pd
import re


# ---------------------------------------------------------------------------
# District-name fix tables
# ---------------------------------------------------------------------------

STATE_FIXES = {
    "MAHARASTRA": "MAHARASHTRA",
    "DELHI": "NCT OF DELHI",
    "A & N ISLANDS": "ANDAMAN & NICOBAR ISLANDS",
    "DADRA AND NAGAR HAVELI": "DADRA AND NAGAR HAVELI & DAMAN AND DIU",
    "DADRA & NAGAR HAVELI": "DADRA AND NAGAR HAVELI & DAMAN AND DIU",
    "DAMAN & DIU": "DADRA AND NAGAR HAVELI & DAMAN AND DIU",
    "DAMAN AND DIU": "DADRA AND NAGAR HAVELI & DAMAN AND DIU",
}


LADAKH_DISTRICTS = {"KARGIL", "LEH LADAKH"}

MANUAL_DISTRICT_FIXES = {
    ("AHMEDABAD", "GUJARAT"): "AHMADABAD",
    ("ARAVALLI", "GUJARAT"): "ARAVALI",
    ("ASHOK NAGAR", "MADHYA PRADESH"): "ASHOKNAGAR",
    ("BAGALKOTE", "KARNATAKA"): "BAGALKOT",
    ("BAGPAT", "UTTAR PRADESH"): "BAGHPAT",
    ("BANDIPORA", "JAMMU & KASHMIR"): "BANDIPORE",
    ("BARABANKI", "UTTAR PRADESH"): "BARA BANKI",
    ("BEMETRA", "CHHATTISGARH"): "BEMETARA",
    ("BRIHAN MUMBAI", "MAHARASHTRA"): "MUMBAI",
    ("BULANDSHAHAR", "UTTAR PRADESH"): "BULANDSHAHR",
    ("CHAMRAJNAGAR", "KARNATAKA"): "CHAMARAJANAGAR",
    ("CHHINDWADA", "MADHYA PRADESH"): "CHHINDWARA",
    ("CHHOTAUDEPUR", "GUJARAT"): "CHHOTA UDAIPUR",
    ("CHIKKABALLAPUR", "KARNATAKA"): "CHIKKABALLAPURA",
    ("DAHOD", "GUJARAT"): "DOHAD",
    ("DEOGARH", "ODISHA"): "DEBAGARH",
    ("EAST CHAMPARAN", "BIHAR"): "PURBA CHAMPARAN",
    ("EAST JAINTIA HILLS", "MEGHALAYA"): "EAST JANTIA HILLS",
    ("JAGATSINGHPUR", "ODISHA"): "JAGATSINGHAPUR",
    ("JANJGIR CHAMPA", "CHHATTISGARH"): "JANJGIR - CHAMPA",
    ("JAYASHANKAR BHUPALPALLY", "TELANGANA"): "JAYASHANKAR BHUPALAPALLY",
    ("KAIMUR BHABUA", "BIHAR"): "KAIMUR (BHABUA)",
    ("KARIM NAGAR", "TELANGANA"): "KARIMNAGAR",
    ("KASHI RAM NAGAR", "UTTAR PRADESH"): "KANSHIRAM NAGAR",
    ("C S M NAGAR", "UTTAR PRADESH"): "KANSHIRAM NAGAR",
    ("KAWARDHA", "CHHATTISGARH"): "KABEERDHAM",
    ("KEONJHAR", "ODISHA"): "KENDUJHAR",
    ("KOMARAM BHEEM", "TELANGANA"): "KOMARAM BHEEM ASIFABAD",
    ("KOZHIKKODE", "KERALA"): "KOZHIKODE",
    ("LAHUL SPITI", "HIMACHAL PRADESH"): "LAHUL & SPITI",
    ("MAHARAJGANJ", "UTTAR PRADESH"): "MAHRAJGANJ",
    ("MAHBUBNAGAR", "TELANGANA"): "MAHABUBNAGAR",
    ("MARIGAON", "ASSAM"): "MORIGAON",
    ("MEDCHAL MALKAJGIRI", "TELANGANA"): "MEDCHAL-MALKAJGIRI",
    ("NARSINGHPUR", "MADHYA PRADESH"): "NARSIMHAPUR",
    ("NICOBAR", "ANDAMAN & NICOBAR ISLANDS"): "NICOBARS",
    ("NORTH AND MIDDLE ANDAMAN", "ANDAMAN & NICOBAR ISLANDS"): "NORTH & MIDDLE ANDAMAN",
    ("NORTH TWENTY FOUR PARGANAS", "WEST BENGAL"): "NORTH TWENTY FOUR PARGANA",
    ("SOUTH TWENTY FOUR PARGANAS", "WEST BENGAL"): "SOUTH TWENTY FOUR PARGANA",
    ("NILGIRIS", "TAMIL NADU"): "THE NILGIRIS",
    ("PONDICHERRY", "PUDUCHERRY"): "PUDUCHERRY",
    ("POONCH", "JAMMU & KASHMIR"): "PUNCH",
    ("RAMANAGAR", "KARNATAKA"): "RAMANAGARA",
    ("RI BHOI", "MEGHALAYA"): "RIBHOI",
    ("SANT RAVIDAS NAGAR", "UTTAR PRADESH"): "SANT RAVIDAS NAGAR (BHADOHI)",
    ("SARAIKELA", "JHARKHAND"): "SARAIKELA-KHARSAWAN",
    ("SHOPIAN", "JAMMU & KASHMIR"): "SHUPIYAN",
    ("SIBSAGAR", "ASSAM"): "SIVASAGAR",
    ("SIDDHARTH NAGAR", "UTTAR PRADESH"): "SIDDHARTHNAGAR",
    ("SINGROLI", "MADHYA PRADESH"): "SINGRAULI",
    ("SIPAHIJALA", "TRIPURA"): "SEPAHIJALA",
    ("SONAPUR", "ODISHA"): "SUBARNAPUR",
    ("TIRUPUR", "TAMIL NADU"): "TIRUPPUR",
    ("TIRUVANAMALAI", "TAMIL NADU"): "TIRUVANNAMALAI",
    ("TOOTHUKUDI", "TAMIL NADU"): "THOOTHUKKUDI",
    ("UNNAV", "UTTAR PRADESH"): "UNNAO",
    ("VISHAKAPATNAM", "ANDHRA PRADESH"): "VISAKHAPATNAM",
    ("YADADRI BHONAGIRI", "TELANGANA"): "YADADRI BHUVANAGIRI",
    ("GURUGRAM", "HARYANA"): "GURGAON",
    ("CUDDAPAH", "ANDHRA PRADESH"): "YSR",
    ("NELLORE", "ANDHRA PRADESH"): "SRI POTTI SRIRAMULU NELLO",
    ("MOHALI SAS NAGAR", "PUNJAB"): "SAHIBZADA AJIT SINGH NAGAR",
    ("MAUNATHBHANJAN", "UTTAR PRADESH"): "MAU",

    # District renamed with region qualifier
    ("KANKER", "CHHATTISGARH"): "UTTAR BASTAR KANKER",
    ("KHARGONE", "MADHYA PRADESH"): "KHARGONE (WEST NIMAR)",

    ("LAKHIMPUR KHERI", "UTTAR PRADESH"): "KHERI",

    ("DADRA AND NAGAR HAVELI", "DADRA AND NAGAR HAVELI & DAMAN AND DIU"): "DADRA & NAGAR HAVELI",
    ("LEH LADAKH", "LADAKH"): "LEH(LADAKH)",
    ("EAST", "SIKKIM"): "EAST DISTRICT",
    ("NORTH", "SIKKIM"): "NORTH DISTRICT",
    ("SOUTH", "SIKKIM"): "SOUTH DISTRICT",
    ("WEST", "SIKKIM"): "WEST DISTRICT",
    ("AIZAWL EAST", "MIZORAM"): "AIZAWL",
    ("AIZAWL WEST", "MIZORAM"): "AIZAWL",
    ("KAMRUP M", "ASSAM"): "KAMRUP",
    ("KAMRUP R", "ASSAM"): "KAMRUP",
    ("BANGALORE URBAN", "KARNATAKA"): "BANGALORE",
    ("KHANDWA", "MADHYA PRADESH"): "KHANDWA (EAST NIMAR)",
    ("KONDAGAON", "CHHATTISGARH"): "KODAGAON",
    ("NAWANSHAHR", "PUNJAB"): "SHAHID BHAGAT SINGH NAGAR",
    ("HATHRAS", "UTTAR PRADESH"): "MAHAMAYA NAGAR",
}


CONFIRMED_UNMATCHABLE = {
    ("ALIPURDUAR", "WEST BENGAL"),
    ("JHARGRAM", "WEST BENGAL"),
    ("KALIMPONG", "WEST BENGAL"),
    ("SAIHA", "MIZORAM"),
}

TRAIN_YEARS = ["2017-2018", "2018-2019"]
TEST_YEAR = "2019-2020"
RISK_PERCENTILE = 0.80   # top 20% of districts (by training-year dropout ratio) = high risk


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def clean_name(name):
    if pd.isna(name):
        return name
    name = str(name).strip()
    name = re.sub(r'\s+', ' ', name)
    name = name.upper()
    name = name.replace('.', '')
    return name


def pivot_and_label(full_df_clean):
    wide_df = full_df_clean.pivot_table(
        index=['District_clean', 'State_clean', 'month', 'fiscal_year'],
        columns='Code',
        values='value',
        aggfunc='sum'
    ).reset_index()

    wide_df.columns.name = None  # remove the "Code" label left over from pivot

    # Rename pentavalent columns for readability
    wide_df = wide_df.rename(columns={
        '9.1.6': 'Penta1',
        '9.1.7': 'Penta2',
        '9.1.8': 'Penta3',
    })

    print(wide_df.shape)
    print(wide_df.head())

    district_year = wide_df.groupby(['District_clean','State_clean', 'fiscal_year'], as_index=False)[
        ['Penta1', 'Penta2', 'Penta3']
    ].sum()

    # Dropout ratio: share of dose-1 recipients who did NOT complete dose-3
    district_year['dropout_ratio'] = (
        (district_year['Penta1'] - district_year['Penta3']) / district_year['Penta1']
    )

    # Guard against divide by zero / negative counts from data errors
    district_year['dropout_ratio'] = district_year['dropout_ratio'].clip(lower=0, upper=1)

    # Compute the threshold using only training-year data
    train_ratios = district_year.loc[district_year['fiscal_year'].isin(TRAIN_YEARS), 'dropout_ratio']

    DROPOUT_THRESHOLD = train_ratios.quantile(RISK_PERCENTILE)

    print(f"Threshold set at {DROPOUT_THRESHOLD:.4f} ({RISK_PERCENTILE*100:.0f}th percentile of training years)")

    # Apply this SAME fixed threshold value to all years (train and test) —
    # this is what makes it a real threshold rather than a leaky, recomputed-per-year cutoff
    district_year['high_dropout_risk'] = (district_year['dropout_ratio'] >= DROPOUT_THRESHOLD).astype(int)

    print("\nOverall label balance:")
    print(district_year['high_dropout_risk'].value_counts())

    print("\nLabel balance within training years only:")
    print(district_year[district_year['fiscal_year'].isin(TRAIN_YEARS)]['high_dropout_risk'].value_counts())

    print("\nLabel balance within test year only:")
    print(district_year[district_year['fiscal_year'] == TEST_YEAR]['high_dropout_risk'].value_counts())

    return district_year


def parse_nfhs5(nfhs5_path):
    """Parse NFHS-5 District-Wise Data."""
    nfhs5_df = pd.read_excel(nfhs5_path, sheet_name="Sheet1")  # Sheet2 is a redundant subset — ignore it

    print("Raw shape:", nfhs5_df.shape)

    # 1. Clean District and State names (strip whitespace, standardize case)
    nfhs5_df['District_clean'] = nfhs5_df['District Names'].apply(clean_name)
    nfhs5_df['State_clean'] = nfhs5_df['State/UT'].apply(clean_name)

    # Fix known state-name inconsistencies you'll want to match against HMIS spellings
    _state_fixes = {"MAHARASTRA": "MAHARASHTRA"}
    nfhs5_df['State_clean'] = nfhs5_df['State_clean'].replace(_state_fixes)

    # 2. Drop columns that leak the target variable
    LEAKAGE_COLS = [
        "Children age 12-23 months who have received 3 doses of penta or DPT vaccine (%)",
        "Children age 12-23 months who have received 3 doses of penta or hepatitis B vaccine (%)",
    ]
    nfhs5_df = nfhs5_df.drop(columns=[c for c in LEAKAGE_COLS if c in nfhs5_df.columns])

    # 3. Confirm no duplicate (District, State) pairs remain
    dupe_check = nfhs5_df.duplicated(subset=['District_clean', 'State_clean']).sum()
    print("Duplicate (District, State) pairs:", dupe_check)
    assert dupe_check == 0, "Unexpected duplicate district-state pairs — investigate before merging"

    # 4. Drop the original raw name columns, keep the cleaned join keys
    nfhs5_df = nfhs5_df.drop(columns=['District Names', 'State/UT'])

    print("Final shape:", nfhs5_df.shape)
    print(nfhs5_df[['District_clean', 'State_clean']].head())

    return nfhs5_df


def apply_district_fix(row):
    key = (row['District_clean'], row['State_clean'])
    return MANUAL_DISTRICT_FIXES.get(key, row['District_clean'])


def merge_with_nfhs5(district_year, nfhs5_df):
    """Apply name fixes and left-merge HMIS district_year with NFHS-5 covariates."""
    print(f"{len(MANUAL_DISTRICT_FIXES)} verified district fixes")
    print(f"{len(CONFIRMED_UNMATCHABLE)} confirmed genuinely absent from NFHS-5 — will remain unmatched")

    merge_df = district_year.copy()

    merge_df.loc[merge_df['District_clean'].isin(LADAKH_DISTRICTS), 'State_clean'] = 'LADAKH'

    merge_df['State_clean'] = merge_df['State_clean'].replace(STATE_FIXES)

    merge_df['District_clean'] = merge_df.apply(apply_district_fix, axis=1)

    nfhs5_df['State_clean'] = nfhs5_df['State_clean'].replace(STATE_FIXES)

    merged_df = merge_df.merge(
        nfhs5_df,
        on=['District_clean', 'State_clean'],
        how='left'
    )

    nfhs5_feature_cols = [c for c in nfhs5_df.columns if c not in ('District_clean', 'State_clean')]

    # Convert all NFHS-5 feature columns to numeric, coercing errors to NaN
    for col in nfhs5_feature_cols:
        merged_df[col] = pd.to_numeric(merged_df[col], errors='coerce')

    unmatched = merged_df[nfhs5_feature_cols].isna().all(axis=1)
    print(f"{unmatched.sum()} of {len(merged_df)} rows still have no NFHS-5 match")

    if unmatched.sum() > 0:
        remaining = merged_df.loc[unmatched, ['District_clean', 'State_clean']].drop_duplicates()
        print("\nRemaining unmatched pairs:")
        print(remaining.to_string())
        print(f"\n(Expected: mostly {len(CONFIRMED_UNMATCHABLE)} confirmed-absent districts — anything else here is new and needs a look)")

    print("\nmerged_df shape:", merged_df.shape)
    return merged_df


if __name__ == "__main__":
    import pandas as pd

    full_df_clean = pd.read_csv("/content/drive/MyDrive/full_df_checkpoint.csv")

    district_year = pivot_and_label(full_df_clean)

    NFHS5_PATH = "/content/drive/MyDrive/NFHS 5 district wise data/ssrn datasheet.xls"
    nfhs5_df = parse_nfhs5(NFHS5_PATH)

    # Save cleaned covariates back to Drive
    nfhs5_df.to_csv("/content/drive/MyDrive/nfhs5_district_clean.csv", index=False)
    print("Saved to /content/drive/MyDrive/nfhs5_district_clean.csv")

    # Re-load (same fix applied to both sides)
    nfhs5_df = pd.read_csv('/content/drive/MyDrive/nfhs5_district_clean.csv')

    # Same state-name fix applied when parsing NFHS-5 — keep both sides consistent
    _fixes = {"MAHARASTRA": "MAHARASHTRA"}
    district_year['State_clean'] = district_year['State_clean'].replace(_fixes)
    nfhs5_df['State_clean'] = nfhs5_df['State_clean'].replace(_fixes)

    # Initial quick merge (diagnostic)
    merged_df_quick = district_year.merge(nfhs5_df, on=['District_clean', 'State_clean'], how='left')
    nfhs5_feature_cols = [c for c in nfhs5_df.columns if c not in ('District_clean', 'State_clean')]
    unmatched = merged_df_quick[nfhs5_feature_cols].isna().all(axis=1)
    print(f"{unmatched.sum()} of {len(merged_df_quick)} rows have no NFHS-5 match")
    if unmatched.sum() > 0:
        print("\nUnmatched (District, State) pairs:")
        print(merged_df_quick.loc[unmatched, ['District_clean', 'State_clean']].drop_duplicates().to_string())
    print("\nmerged_df shape:", merged_df_quick.shape)

    merged_df = merge_with_nfhs5(district_year, nfhs5_df)

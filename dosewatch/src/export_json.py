# -*- coding: utf-8 -*-
"""export_json.py — Assemble per-district predictions + SHAP drivers and write JSON."""

import json
import os
import numpy as np


TOP_N_DRIVERS = 5  # how many drivers to show per district card


def build_output(X_test, test_df, shap_values_normalized, y_pred, y_proba):
    feature_names = X_test.columns.tolist()
    district_names = test_df['District_clean'].values
    state_names = test_df['State_clean'].values

    output = []

    for i in range(len(X_test)):
        district_shap = shap_values_normalized[i]  # 108 values for this district

        # Get indices of the top N drivers by absolute magnitude
        top_idx = np.argsort(np.abs(district_shap))[::-1][:TOP_N_DRIVERS]

        drivers = []
        for idx in top_idx:
            drivers.append({
                "feature": feature_names[idx],
                "value": round(float(district_shap[idx]), 4),
                "direction": "increases_risk" if district_shap[idx] > 0 else "decreases_risk"
            })

        output.append({
            "district": district_names[i],
            "state": state_names[i],
            "risk_score": round(float(y_proba[i]), 4),
            "risk_label": "HIGH" if y_pred[i] == 1 else "LOW",
            "top_drivers": drivers
        })

    print("Total districts exported:", len(output))
    print(json.dumps(output[0], indent=2))  # sanity check: preview the first district

    return output


def save_json(output, output_path):
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print("Saved to:", output_path)
    print("File size:", os.path.getsize(output_path) / 1024, "KB")


if __name__ == "__main__":
    # Importing here to avoid circular deps when used as a library
    import pandas as pd
    from train_model import split_train_test, train_and_evaluate, DROP_COLS
    from shap_export import compute_shap

    merged_df = pd.read_csv("/content/drive/MyDrive/merged_df.csv")
    train_df, test_df = split_train_test(merged_df)
    model, X_test, y_pred, y_proba = train_and_evaluate(train_df, test_df)
    shap_values_normalized = compute_shap(model, X_test)

    output = build_output(X_test, test_df, shap_values_normalized, y_pred, y_proba)

    output_path = "/content/drive/MyDrive/dosewatch_predictions.json"
    save_json(output, output_path)

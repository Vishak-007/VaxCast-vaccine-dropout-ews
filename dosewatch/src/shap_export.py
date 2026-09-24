# -*- coding: utf-8 -*-
"""shap_export.py — Compute and normalise SHAP values for the test set."""

import shap
import numpy as np


def compute_shap(model, X_test):
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_test)

    # Check what shape/format we actually got
    print(type(shap_values))
    if isinstance(shap_values, list):
        print("List of arrays, shapes:", [s.shape for s in shap_values])
    else:
        print("Array shape:", shap_values.shape)
    shap_values_class1 = shap_values[:, :, 1]
    print(shap_values_class1.shape)

    global_max_abs = np.abs(shap_values_class1).max()
    print("Global max absolute SHAP value:", global_max_abs)

    shap_values_normalized = shap_values_class1 / global_max_abs
    print("Normalized range:", shap_values_normalized.min(), "to", shap_values_normalized.max())

    return shap_values_normalized

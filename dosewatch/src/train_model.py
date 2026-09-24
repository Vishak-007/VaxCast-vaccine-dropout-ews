# -*- coding: utf-8 -*-
"""train_model.py — Temporal train/test split and Random Forest training."""

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, roc_auc_score

TRAIN_YEARS = ["2017-2018", "2018-2019"]
TEST_YEAR = "2019-2020"

DROP_COLS = ['District_clean', 'State_clean', 'fiscal_year', 'high_dropout_risk', 'dropout_ratio']


def split_train_test(merged_df):
    # STEP 6 — Temporal train-test split
    train_df = merged_df[merged_df['fiscal_year'].isin(TRAIN_YEARS)].copy()
    test_df = merged_df[merged_df['fiscal_year'] == TEST_YEAR].copy()

    print("Train shape:", train_df.shape)
    print("Test shape:", test_df.shape)

    print("\nTrain label balance:")
    print(train_df['high_dropout_risk'].value_counts())

    print("\nTest label balance:")
    print(test_df['high_dropout_risk'].value_counts())

    return train_df, test_df


def train_and_evaluate(train_df, test_df):
    X_train = train_df.drop(columns=DROP_COLS)
    y_train = train_df['high_dropout_risk']

    X_test = test_df.drop(columns=DROP_COLS)
    y_test = test_df['high_dropout_risk']

    model = RandomForestClassifier(
        n_estimators=300,
        max_depth=8,
        min_samples_leaf=5,
        class_weight='balanced',
        random_state=42
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]

    print(classification_report(y_test, y_pred))
    print("ROC-AUC:", roc_auc_score(y_test, y_proba).round(3))

    return model, X_test, y_pred, y_proba


if __name__ == "__main__":
    merged_df = pd.read_csv("/content/drive/MyDrive/merged_df.csv")

    train_df, test_df = split_train_test(merged_df)

    train_df.to_csv('/content/drive/MyDrive/train_df.csv', index=False)
    test_df.to_csv('/content/drive/MyDrive/test_df.csv', index=False)
    print("\nSaved train_df.csv and test_df.csv to Drive")

    model, X_test, y_pred, y_proba = train_and_evaluate(train_df, test_df)

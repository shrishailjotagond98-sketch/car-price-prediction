"""Train and evaluate the car-price model.

Run from any directory with: python backend/train.py
"""

import json
import os

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor, GradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, median_absolute_error, r2_score
from sklearn.model_selection import GroupKFold, cross_val_predict

from models.car_price_model import FEATURES, MODEL_PATH, build_model

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_CSV = os.path.join(BASE_DIR, "data", "quikr_car.csv")
CLEAN_CSV = os.path.join(BASE_DIR, "data", "cleaned.csv")
METRICS_PATH = os.path.join(BASE_DIR, "models", "metrics.json")


def clean(data: pd.DataFrame) -> pd.DataFrame:
    required = {"name", "company", "year", "Price", "kms_driven", "fuel_type"}
    missing = required.difference(data.columns)
    if missing:
        raise ValueError(f"Dataset is missing required columns: {', '.join(sorted(missing))}")

    df = data.copy()
    for column in ("name", "company", "fuel_type"):
        df[column] = df[column].astype("string").str.strip()

    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["Price"] = pd.to_numeric(
        df["Price"].astype("string").str.replace(",", "", regex=False)
        .replace("Ask For Price", pd.NA),
        errors="coerce",
    )
    kms_text = df["kms_driven"].astype("string").str.extract(r"^\s*([\d,]+)", expand=False)
    df["kms_driven"] = pd.to_numeric(
        kms_text.str.replace(",", "", regex=False), errors="coerce"
    )

    df = df.dropna(subset=["name", "company", "year", "Price", "kms_driven", "fuel_type"])
    df = df[
        df["year"].between(1900, 2100)
        & df["year"].mod(1).eq(0)
        & df["Price"].gt(0)
        & df["Price"].lt(6_000_000)
        & df["kms_driven"].between(0, 499_999)
    ].copy()

    df["year"] = df["year"].astype(int)
    df["Price"] = df["Price"].astype(int)
    df["kms_driven"] = df["kms_driven"].astype(int)
    df["name"] = df["name"].str.split().str[:3].str.join(" ")
    df["company"] = df["company"].str.title()
    df["fuel_type"] = df["fuel_type"].str.title()

    company_counts = df["company"].value_counts()
    df = df[df["company"].isin(company_counts[company_counts >= 5].index)]
    df = df.drop_duplicates().reset_index(drop=True)
    if df.empty:
        raise ValueError("No valid car listings remain after cleaning the dataset.")
    return df


def candidates():
    return {
        "Extra Trees": ExtraTreesRegressor(
            n_estimators=300,
            max_features=1.0,
            random_state=42,
            n_jobs=-1,
        ),
        "Random Forest": RandomForestRegressor(
            n_estimators=300,
            max_features=1.0,
            random_state=42,
            n_jobs=-1,
        ),
        "Gradient Boosting": GradientBoostingRegressor(
            n_estimators=250,
            learning_rate=0.04,
            max_depth=2,
            loss="huber",
            random_state=42,
        ),
    }


def main():
    df = clean(pd.read_csv(RAW_CSV))
    X = df[FEATURES]
    y = np.log1p(df["Price"].astype(float))

    groups = pd.MultiIndex.from_frame(X.astype(str)).factorize()[0]
    group_count = int(np.unique(groups).size)
    if group_count < 2:
        raise ValueError("At least two distinct car configurations are required for training.")
    cv = GroupKFold(n_splits=min(5, group_count))

    comparison = []
    predictions_by_model = {}
    for name, estimator in candidates().items():
        pipeline = build_model(estimator)
        predicted_log = cross_val_predict(
            pipeline, X, y, groups=groups, cv=cv, n_jobs=1
        )
        predicted_price = np.maximum(0, np.expm1(predicted_log))
        actual_price = df["Price"].to_numpy(dtype=float)
        scores = {
            "model": name,
            "cv_r2": round(float(r2_score(actual_price, predicted_price)), 3),
            "cv_mae": int(round(mean_absolute_error(actual_price, predicted_price))),
            "cv_median_ae": int(round(median_absolute_error(actual_price, predicted_price))),
        }
        comparison.append(scores)
        predictions_by_model[name] = predicted_log
        print(f"{name}: grouped CV MAE = Rs {scores['cv_mae']:,}, R2 = {scores['cv_r2']:.3f}")

    best_name = min(comparison, key=lambda item: item["cv_mae"])["model"]
    predicted_log = predictions_by_model[best_name]
    actual_price = df["Price"].to_numpy(dtype=float)
    predicted_price = np.maximum(0, np.expm1(predicted_log))
    residuals = y.to_numpy() - predicted_log
    metrics = {
        "best_model": best_name,
        "rows": int(len(df)),
        "r2": round(float(r2_score(actual_price, predicted_price)), 3),
        "mae": int(round(mean_absolute_error(actual_price, predicted_price))),
        "median_ae": int(round(median_absolute_error(actual_price, predicted_price))),
        "resid_q10": float(np.quantile(residuals, 0.10)),
        "resid_q90": float(np.quantile(residuals, 0.90)),
        "validation": f"{cv.get_n_splits()}-fold grouped cross-validation",
        "comparison": comparison,
        "test_points": [
            {"actual": int(actual), "predicted": int(round(predicted))}
            for actual, predicted in zip(actual_price, predicted_price)
        ],
    }

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    df.to_csv(CLEAN_CSV, index=False)
    best_model = build_model(candidates()[best_name]).fit(X, y)

    model_tmp = MODEL_PATH + ".tmp"
    metrics_tmp = METRICS_PATH + ".tmp"
    joblib.dump(best_model, model_tmp)
    with open(metrics_tmp, "w", encoding="utf-8") as metrics_file:
        json.dump(metrics, metrics_file, indent=2)
    os.replace(model_tmp, MODEL_PATH)
    os.replace(metrics_tmp, METRICS_PATH)

    print(
        f"Trained {best_name} on {len(df)} cleaned rows. "
        f"Grouped CV MAE = Rs {metrics['mae']:,}; R2 = {metrics['r2']:.3f}"
    )
    print(f"Saved model: {MODEL_PATH}")
    print(f"Saved metrics: {METRICS_PATH}")


if __name__ == "__main__":
    main()

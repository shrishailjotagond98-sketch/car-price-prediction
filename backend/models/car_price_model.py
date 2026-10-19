"""Model factory and loader for the serialized car-price pipeline."""

import os

import joblib
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

MODEL_PATH = os.path.join(os.path.dirname(__file__), "car_price_model.joblib")
FEATURES = ["name", "company", "year", "kms_driven", "fuel_type"]
CATEGORICAL_FEATURES = ["name", "company", "fuel_type"]


def build_model(estimator):
    preprocessor = ColumnTransformer(
        [
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                CATEGORICAL_FEATURES,
            )
        ],
        remainder="passthrough",
    )
    return Pipeline([("preprocessor", preprocessor), ("regressor", estimator)])


def load_model():
    if not os.path.isfile(MODEL_PATH):
        raise FileNotFoundError(
            f"Trained model not found at {MODEL_PATH}. Run `python train.py` from backend first."
        )
    return joblib.load(MODEL_PATH)

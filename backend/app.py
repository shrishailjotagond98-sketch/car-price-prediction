"""Car price prediction API + dashboard server.

Run from the backend folder:  python app.py
Then open http://127.0.0.1:5000
"""
import json
import math
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

import numpy as np
import pandas as pd
from flask import Flask, jsonify, request, send_from_directory

from models.car_price_model import FEATURES, load_model

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")
DB_PATH = os.path.join(BASE_DIR, "history.db")
DATA_PATH = os.path.join(BASE_DIR, "data", "cleaned.csv")
METRICS_PATH = os.path.join(BASE_DIR, "models", "metrics.json")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")

# ---------- load model + data once at startup ----------
model = load_model()
if not os.path.isfile(METRICS_PATH) or not os.path.isfile(DATA_PATH):
    raise FileNotFoundError("Model artifacts are incomplete. Run `python train.py` from backend.")
with open(METRICS_PATH, encoding="utf-8") as f:
    metrics = json.load(f)
df = pd.read_csv(DATA_PATH)
required_columns = set(FEATURES) | {"Price"}
missing_columns = required_columns.difference(df.columns)
if missing_columns:
    raise ValueError(f"Cleaned dataset is missing columns: {', '.join(sorted(missing_columns))}")

YEAR_MIN, YEAR_MAX = int(df["year"].min()), int(df["year"].max())
COMPANIES = set(df["company"].astype(str))
CAR_CONFIGURATIONS = set(
    zip(df["company"].astype(str), df["name"].astype(str), df["fuel_type"].astype(str))
)


# ---------- history database (SQLite) ----------
@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with db() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                company TEXT NOT NULL,
                name TEXT NOT NULL,
                year INTEGER NOT NULL,
                kms_driven INTEGER NOT NULL,
                fuel_type TEXT NOT NULL,
                price INTEGER NOT NULL,
                low INTEGER NOT NULL,
                high INTEGER NOT NULL
            )"""
        )


init_db()


def parse_integer(value):
    if isinstance(value, bool):
        raise ValueError("Boolean values are not valid integers.")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdecimal():
        return int(value.strip())
    raise ValueError("Expected a whole number.")


# ---------- pages ----------
@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


# ---------- API ----------
@app.get("/api/options")
def options():
    """Values for the prediction form dropdowns."""
    models_by_company = {
        c: g["name"].value_counts().index.tolist() for c, g in df.groupby("company")
    }
    fuels_by_model = {
        company: {
            name: sorted(model_rows["fuel_type"].dropna().unique().tolist())
            for name, model_rows in company_rows.groupby("name")
        }
        for company, company_rows in df.groupby("company")
    }
    companies = df["company"].value_counts().index.tolist()
    return jsonify(
        companies=companies,
        models=models_by_company,
        model_fuels=fuels_by_model,
        fuel_types=sorted(df["fuel_type"].unique().tolist()),
        year_min=YEAR_MIN,
        year_max=YEAR_MAX,
    )


@app.get("/api/summary")
def summary():
    """Numbers for the home page."""
    with db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
        last = conn.execute("SELECT * FROM predictions ORDER BY id DESC LIMIT 1").fetchone()
    return jsonify(
        rows=int(len(df)),
        brands=int(df["company"].nunique()),
        models=int(df["name"].nunique()),
        r2=metrics["r2"],
        mae=metrics["mae"],
        best_model=metrics["best_model"],
        predictions=count,
        last=dict(last) if last else None,
    )


@app.post("/api/predict")
def predict():
    data = request.get_json(silent=True) or {}
    try:
        company = str(data["company"]).strip()
        name = str(data["name"]).strip()
        year = parse_integer(data["year"])
        kms = parse_integer(data["kms_driven"])
        fuel = str(data["fuel_type"]).strip()
    except (KeyError, ValueError, TypeError):
        return jsonify(error="Fill in every field with valid values."), 400

    if not company or not name or not fuel:
        return jsonify(error="Fill in every field with valid values."), 400
    if company not in COMPANIES:
        return jsonify(error="Choose a brand from the available options."), 400
    if (company, name, fuel) not in CAR_CONFIGURATIONS:
        return jsonify(error="Choose a model and fuel type from the available options."), 400
    if not (YEAR_MIN <= year <= YEAR_MAX):
        return jsonify(error=f"Year must be between {YEAR_MIN} and {YEAR_MAX}."), 400
    if not (0 <= kms <= 500_000):
        return jsonify(error="Kilometres driven must be between 0 and 500,000."), 400

    row = pd.DataFrame(
        [{"name": name, "company": company, "year": year, "kms_driven": kms, "fuel_type": fuel}]
    )
    predicted_log_price = float(model.predict(row)[0])
    predicted_values = [
        float(np.expm1(predicted_log_price)),
        float(np.expm1(predicted_log_price + metrics["resid_q10"])),
        float(np.expm1(predicted_log_price + metrics["resid_q90"])),
    ]
    if not all(math.isfinite(value) for value in predicted_values):
        raise ValueError("The model returned a non-finite car price.")
    price, low, high = (max(0, int(round(value, -3))) for value in predicted_values)
    low = min(low, price)
    high = max(high, price)

    with db() as conn:
        cur = conn.execute(
            """INSERT INTO predictions
               (created_at, company, name, year, kms_driven, fuel_type, price, low, high)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (datetime.now().isoformat(timespec="seconds"), company, name, year, kms, fuel,
             price, low, high),
        )
        new_id = cur.lastrowid
    return jsonify(id=new_id, price=price, low=low, high=high)


@app.get("/api/history")
def history():
    with db() as conn:
        rows = conn.execute("SELECT * FROM predictions ORDER BY id DESC").fetchall()
    return jsonify([dict(r) for r in rows])


@app.delete("/api/history/<int:pid>")
def delete_one(pid):
    with db() as conn:
        conn.execute("DELETE FROM predictions WHERE id = ?", (pid,))
    return jsonify(ok=True)


@app.delete("/api/history")
def delete_all():
    with db() as conn:
        conn.execute("DELETE FROM predictions")
    return jsonify(ok=True)


@app.get("/api/analytics")
def analytics():
    # average price + count by brand (top 10 by listings)
    by_brand = (
        df.groupby("company")["Price"].agg(["mean", "count"]).sort_values("count", ascending=False)
        .head(10).reset_index()
    )
    # average price by manufacturing year (years with >= 3 listings)
    by_year = df.groupby("year")["Price"].agg(["mean", "count"]).reset_index()
    by_year = by_year[by_year["count"] >= 3]
    # fuel split
    fuel = df.groupby("fuel_type")["Price"].agg(["mean", "count"]).reset_index()
    # kms vs price sample
    sample = df.sample(min(300, len(df)), random_state=1)

    with db() as conn:
        h = conn.execute(
            "SELECT COUNT(*) AS n, AVG(price) AS avg_price FROM predictions"
        ).fetchone()
        top = conn.execute(
            "SELECT company, COUNT(*) AS n FROM predictions GROUP BY company ORDER BY n DESC LIMIT 1"
        ).fetchone()

    return jsonify(
        by_brand=[
            {"company": r.company, "avg_price": int(r["mean"]), "count": int(r["count"])}
            for _, r in by_brand.iterrows()
        ],
        by_year=[
            {"year": int(r["year"]), "avg_price": int(r["mean"]), "count": int(r["count"])}
            for _, r in by_year.iterrows()
        ],
        fuel=[
            {"fuel_type": r["fuel_type"], "avg_price": int(r["mean"]), "count": int(r["count"])}
            for _, r in fuel.iterrows()
        ],
        kms_price=[{"x": int(k), "y": int(p)} for k, p in zip(sample["kms_driven"], sample["Price"])],
        model={
            "best_model": metrics["best_model"],
            "r2": metrics["r2"],
            "mae": metrics["mae"],
            "comparison": metrics["comparison"],
            "test_points": metrics["test_points"],
        },
        my_predictions={
            "count": h["n"],
            "avg_price": int(h["avg_price"]) if h["avg_price"] else 0,
            "top_brand": top["company"] if top else None,
        },
    )


if __name__ == "__main__":
    app.run(debug=False, use_reloader=False)

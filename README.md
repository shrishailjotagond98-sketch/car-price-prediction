# CarWorth: used car price prediction

Machine learning dashboard built on the Quikr used-car dataset.
Pages: Home, Predict, History, Analytics.

## Structure
```
car-price-prediction/
├── backend/
│   ├── app.py              Flask API + serves the frontend
│   ├── train.py            cleans data, trains and saves the model
│   ├── requirements.txt
│   ├── data/               quikr_car.csv (raw), cleaned.csv (made by train.py)
│   ├── models/             car_price_model.py, car_price_model.joblib, metrics.json
│   └── history.db          SQLite, created on first run
└── frontend/
    ├── index.html
    ├── css/style.css
    └── js/app.js
```

## Run
```
cd backend
pip install -r requirements.txt
python train.py        # only needed once, or after changing the data
python app.py
```
Open http://127.0.0.1:5000

Training evaluates Extra Trees, Random Forest, and Gradient Boosting with grouped cross-validation so identical car inputs are not split between training and validation. The selected model, cleaned data, and validation metrics are saved by `train.py`. Predictions are estimates, not guaranteed sale prices; the available dataset contains only a limited number of listings.

Charts load Chart.js from a CDN, so the Analytics page needs internet.

## API
| Method | Route | Purpose |
|---|---|---|
| GET | /api/options | brands, models, fuel types, year range |
| GET | /api/summary | home page numbers |
| POST | /api/predict | returns price + range, saves to history |
| GET | /api/history | all saved predictions |
| DELETE | /api/history/<id> | delete one |
| DELETE | /api/history | clear all |
| GET | /api/analytics | chart data |

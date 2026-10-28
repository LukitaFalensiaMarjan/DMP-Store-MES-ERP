import pandas as pd
import joblib
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier

def train_models():
    # 1. Training model regresi untuk estimasi waktu selesai order (ETA)
    df_eta = pd.read_csv("ai_models/dataset_order_eta.csv")
    X_eta = df_eta[["order_qty", "machine_speed", "active_queues", "stock_ready", "avg_machine_health"]]
    y_eta = df_eta["estimated_days"]

    model_eta = RandomForestRegressor(n_estimators=100, random_state=42)
    model_eta.fit(X_eta, y_eta)
    joblib.dump(model_eta, "ai_models/model_eta.pkl")
    print("Model AI Estimasi Waktu (model_eta.pkl) berhasil dibuat.")

    # 2. Training model klasifikasi untuk kelayakan order (Supervisi)
    df_feas = pd.read_csv("ai_models/dataset_feasibility.csv")
    X_feas = df_feas[["stock_coverage_pct", "machine_health", "days_margin"]]
    y_feas = df_feas["is_feasible"]

    model_feas = RandomForestClassifier(n_estimators=100, random_state=42)
    model_feas.fit(X_feas, y_feas)
    joblib.dump(model_feas, "ai_models/model_feasibility.pkl")
    print("Model AI Kelayakan Order (model_feasibility.pkl) berhasil dibuat.")

if __name__ == "__main__":
    train_models()
"""Chargement du modele Random Forest (une seule fois, au demarrage) et fonction de prediction."""
import json
import os
import joblib
import pandas as pd

ML_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ml_model")

model = joblib.load(os.path.join(ML_DIR, "model.pkl"))
scaler = joblib.load(os.path.join(ML_DIR, "scaler.pkl"))
quartier_freq = joblib.load(os.path.join(ML_DIR, "quartier_freq.pkl"))
feature_columns = joblib.load(os.path.join(ML_DIR, "feature_columns.pkl"))
mode_par_ville = joblib.load(os.path.join(ML_DIR, "mode_par_ville.pkl"))

with open(os.path.join(ML_DIR, "metrics.json"), encoding="utf-8") as f:
    metrics = json.load(f)

ville_columns = [c for c in feature_columns if c.startswith("ville_")]
villes_disponibles = sorted([c.replace("ville_", "") for c in ville_columns])

cols_numeriques = ['Surface_m2', 'Pieces', 'Chambres', 'Salles_Bain', 'Quartier_freq']

TYPE_MAP = {
    "appartement": "type_appartement",
    "studio": "type_studio",
    "maison": "type_maison",
    "villa": "type_villa",
    "duplex": "type_duplex",
}


def predict_price(ville, quartier, type_bien, surface, pieces, chambres, salles_bain,
                   haut_standing=0, en_construction=0):
    row = {col: 0 for col in feature_columns}

    type_col = TYPE_MAP.get(type_bien.lower(), "type_appartement")
    if type_col in row:
        row[type_col] = 1

    row["Surface_m2"] = surface
    row["Pieces"] = pieces
    row["Chambres"] = chambres
    row["Salles_Bain"] = salles_bain
    if "Is_Haut_Standing" in row:
        row["Is_Haut_Standing"] = haut_standing
    if "En_Construction" in row:
        row["En_Construction"] = en_construction

    freq = quartier_freq.get(quartier, quartier_freq.median())
    row["Quartier_freq"] = freq

    ville_col = f"ville_{ville}"
    if ville_col in row:
        row[ville_col] = 1

    X = pd.DataFrame([row])[feature_columns]
    X = X.drop(columns=["Surface_x_Quartier"])
    X[cols_numeriques] = scaler.transform(X[cols_numeriques])
    X["Surface_x_Quartier"] = X["Surface_m2"] * X["Quartier_freq"]
    X = X[feature_columns]

    pred = model.predict(X)[0]
    rmse = metrics["random_forest_clean"]["rmse"]

    return {
        "prix_estime": round(float(pred)),
        "prix_min": round(float(pred) - rmse),
        "prix_max": round(float(pred) + rmse),
        "prix_par_m2": round(float(pred) / surface) if surface else 0,
    }

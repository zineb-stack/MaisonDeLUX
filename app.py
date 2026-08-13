"""
API Flask — MaisonLux Maroc
Sert le modèle Random Forest entraîné sur les données réelles (maisonlux_maroc_complet.csv).
"""
import json
import numpy as np
import pandas as pd
import joblib
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

model = joblib.load("model.pkl")
scaler = joblib.load("scaler.pkl")
quartier_freq = joblib.load("quartier_freq.pkl")
feature_columns = joblib.load("feature_columns.pkl")
mode_par_ville = joblib.load("mode_par_ville.pkl")

with open("metrics.json", encoding="utf-8") as f:
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


@app.route("/api/villes", methods=["GET"])
def get_villes():
    return jsonify({"villes": villes_disponibles})


@app.route("/api/metrics", methods=["GET"])
def get_metrics():
    return jsonify(metrics)


@app.route("/api/predict", methods=["POST"])
def predict():
    data = request.get_json(force=True)

    ville = data.get("ville", "")
    quartier = data.get("quartier", "").strip()
    type_bien = data.get("type_bien", "appartement").lower()
    surface = float(data.get("surface", 0))
    pieces = float(data.get("pieces", 1))
    chambres = float(data.get("chambres", 1))
    salles_bain = float(data.get("salles_bain", 1))
    haut_standing = int(data.get("haut_standing", 0))
    en_construction = int(data.get("en_construction", 0))

    if surface <= 0:
        return jsonify({"error": "La surface doit être supérieure à 0."}), 400

    row = {col: 0 for col in feature_columns}

    type_col = TYPE_MAP.get(type_bien, "type_appartement")
    if type_col in row:
        row[type_col] = 1

    row["Surface_m2"] = surface
    row["Pieces"] = pieces
    row["Chambres"] = chambres
    row["Salles_Bain"] = salles_bain
    row["Is_Haut_Standing"] = haut_standing
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

    return jsonify({
        "prix_estime": round(float(pred)),
        "prix_min": round(float(pred) - rmse),
        "prix_max": round(float(pred) + rmse),
        "prix_par_m2": round(float(pred) / surface),
        "ville": ville,
        "quartier": quartier if quartier else "Non renseigné",
    })


@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "status": "ok",
        "message": "API MaisonLux Maroc — Random Forest",
        "endpoints": ["/api/predict (POST)", "/api/villes (GET)", "/api/metrics (GET)"]
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)
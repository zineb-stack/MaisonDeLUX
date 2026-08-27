"""
API Flask — MaisonLux Maroc
Sert la pipeline de régression finale entraînée sur les données immobilières auditées.
"""
import json
from pathlib import Path

import pandas as pd
import joblib
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
app.url_map.strict_slashes = False

ARTIFACTS_DIR = Path(__file__).resolve().parents[1] / "ml" / "artifacts"

model = joblib.load(ARTIFACTS_DIR / "pipeline.pkl")

with open(ARTIFACTS_DIR / "metrics.json", encoding="utf-8") as f:
    metrics = json.load(f)

with open(ARTIFACTS_DIR / "model_metadata.json", encoding="utf-8") as f:
    model_metadata = json.load(f)

villes_disponibles = model_metadata["cities"]
TYPES_DISPONIBLES = {"appartement", "studio", "maison", "villa", "duplex"}


@app.route("/api/villes", methods=["GET"])
def get_villes():
    return jsonify({"villes": villes_disponibles})


@app.route("/api/metrics", methods=["GET"])
def get_metrics():
    # Alias conservé pour le dashboard historique, sans modifier le fichier de métriques scientifique.
    payload = dict(metrics)
    payload["random_forest_clean"] = dict(metrics["final_model"]["test"])
    payload["n_samples"] = metrics["final_model"]["n_training_full_refit"]
    return jsonify(payload)


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

    if type_bien not in TYPES_DISPONIBLES:
        type_bien = "appartement"

    model_input = pd.DataFrame([{
        "Surface_m2": surface,
        "Pieces": pieces,
        "Chambres": chambres,
        "Salles_Bain": salles_bain,
        "Is_Haut_Standing": haut_standing,
        "En_Construction": en_construction,
        "Type_Bien": type_bien,
        "Ville": ville,
        "Quartier": quartier if quartier else "Non renseigné",
    }])

    pred = model.predict(model_input)[0]
    rmse = metrics["final_model"]["test"]["rmse"]

    return jsonify({
        "prix_estime": round(float(pred)),
        "prix_min": round(max(0, float(pred) - rmse)),
        "prix_max": round(float(pred) + rmse),
        "prix_par_m2": round(float(pred) / surface),
        "ville": ville,
        "quartier": quartier if quartier else "Non renseigné",
    })


@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "status": "ok",
        "message": "API MaisonLux Maroc — modèle final Phase 4",
        "endpoints": ["/api/predict (POST)", "/api/villes (GET)", "/api/metrics (GET)"]
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)

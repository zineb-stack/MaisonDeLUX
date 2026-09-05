"""MaisonDeLUX V1 inference. Run from the repository: python -m backend.app."""
import json
import math
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

ROOT = Path(__file__).resolve().parents[1]
model = joblib.load(ROOT / 'models/maisondelux_price_model_v1.joblib')
metadata = json.loads((ROOT / 'models/maisondelux_price_model_v1_metadata.json').read_text(encoding='utf-8'))
locations = json.loads((ROOT / 'models/locations_v1.json').read_text(encoding='utf-8'))
FEATURES = metadata['features']
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024


def validate(data):
    if not isinstance(data, dict):
        raise ValueError('Un objet JSON est requis.')
    if set(data) - set(FEATURES):
        raise ValueError('Le formulaire contient des champs non pris en charge.')
    row = {}
    for key in FEATURES[:3]:
        value = data.get(key)
        if key != 'surface_m2' and (value is None or value == ''):
            row[key] = np.nan
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f'{key} doit être numérique.')
        if not math.isfinite(value) or (value <= 0 if key == 'surface_m2' else value < 0):
            raise ValueError(f'{key} doit être fini et positif.')
        if key != 'surface_m2' and value != int(value):
            raise ValueError(f'{key} doit être entier.')
        row[key] = value
    for key in FEATURES[3:]:
        value = data.get(key)
        if value is not None and not isinstance(value, str):
            raise ValueError(f'{key} doit être du texte.')
        value = value.strip() if value else ''
        if len(value) > 200:
            raise ValueError(f'{key} est trop long.')
        if key in ('city', 'region', 'property_type') and not value:
            raise ValueError(f'{key} est requis.')
        row[key] = value or ('unknown' if key in FEATURES[7:] else np.nan)
    return pd.DataFrame([row], columns=FEATURES)


@app.errorhandler(HTTPException)
def http_error(error):
    return jsonify(error=error.description), error.code


@app.post('/api/estimate')
def estimate():
    try:
        frame = validate(request.get_json())
    except ValueError as error:
        return jsonify(error=str(error)), 400
    try:
        price = float(model.predict(frame)[0])
        if not math.isfinite(price) or price <= 0:
            raise ValueError('Invalid model output')
    except Exception:
        app.logger.exception('Inference failed')
        return jsonify(error="Le service d'estimation est momentanément indisponible."), 503
    return jsonify(estimated_price_mad=round(price), currency='MAD', model_version='v1')


@app.get('/api/villes')
def cities():
    return jsonify(villes=sorted(locations))


@app.get('/api/metrics')
def metrics():
    return jsonify(**metadata, currency='MAD', model_version='v1')


@app.get('/')
def health():
    return jsonify(status='ok', model_version='v1')


if __name__ == '__main__':
    app.run(port=5000, debug=False)

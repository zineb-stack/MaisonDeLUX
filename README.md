# MaisonLux Maroc — Backend (Random Forest réel)

## Installation

```bash
pip install -r requirements.txt
```

## Lancer l'API

```bash
python app.py
```

L'API tourne sur `http://localhost:5000`.

## Endpoints

### `POST /api/predict`
Body JSON :
```json
{
  "ville": "Casablanca",
  "quartier": "Maarif",
  "type_bien": "appartement",
  "surface": 90,
  "pieces": 3,
  "chambres": 2,
  "salles_bain": 1
}
```
Réponse :
```json
{
  "prix_estime": 1006897,
  "prix_min": 407190,
  "prix_max": 1606604,
  "prix_par_m2": 11188,
  "ville": "Casablanca",
  "quartier": "Maarif"
}
```

### `GET /api/villes`
Liste des villes reconnues par le modèle (140 villes).

### `GET /api/metrics`
Métriques du modèle (RMSE, MAE, R² pour chaque modèle testé).

## Réentraîner le modèle

Si tu changes le CSV, relance :
```bash
python train_model.py
```
Ça régénère `model.pkl`, `scaler.pkl`, `quartier_freq.pkl`, `feature_columns.pkl`, `mode_par_ville.pkl` et `metrics.json`.

## Fichiers

- `train_model.py` — pipeline complet (nettoyage + preprocessing + entraînement)
- `app.py` — API Flask
- `model.pkl` — Random Forest entraîné (données nettoyées)
- `scaler.pkl` — StandardScaler pour les colonnes numériques
- `quartier_freq.pkl` — fréquences des quartiers (encodage)
- `feature_columns.pkl` — ordre exact des colonnes attendues par le modèle
- `mode_par_ville.pkl` — quartier le plus fréquent par ville (imputation)
- `metrics.json` — performances des modèles (RMSE, MAE, R²)
- `maisonlux_maroc_complet.csv` — données brutes
- `df_clean.csv` — données nettoyées (après pipeline)

## Connecter le frontend

Dans `site.html`, remplace la fonction `estimForm.addEventListener('submit', ...)` par un appel `fetch` vers `http://localhost:5000/api/predict`. Demande-moi et je te fais la modification directement.

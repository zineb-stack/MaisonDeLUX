# MaisonDeLUX

Application web d'estimation immobilière au Maroc, avec un frontend HTML et une API Flask utilisant une pipeline de régression scikit-learn.

## Installation

```bash
pip install -r requirements.txt
```

## Lancer l'API

Depuis la racine du projet :

```bash
python backend/app.py
```

L'API tourne sur `http://localhost:5000`.

## Ouvrir le frontend

Ouvrir `frontend/site.html` dans un navigateur. Les pages `login.html`, `signup.html` et `dashboard.html` restent liées entre elles par des chemins relatifs.

## Endpoints

- `POST /api/predict` : retourne l'estimation d'un bien.
- `GET /api/villes` : retourne la liste des villes reconnues par le modèle.
- `GET /api/metrics` : retourne les métriques enregistrées du modèle.

Exemple de requête pour `POST /api/predict` :

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

Exemple de réponse :

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

## Organisation

- `backend/` : API Flask.
- `frontend/` : pages HTML et répertoires d'assets.
- `ml/notebooks/` : notebooks historiques et notebook final reproductible.
- `ml/src/` : scripts liés à la collecte et au traitement des données.
- `ml/artifacts/` : pipeline de production, métadonnées, métriques et artefacts historiques.
- `data/raw/` : données sources.
- `data/processed/` : emplacement réservé aux données transformées.
- `tests/` : emplacement réservé aux tests.
- `docs/` : documentation complémentaire.

Les artefacts utilisés directement par l'API sont :

- `ml/artifacts/pipeline.pkl` : pipeline finale de prétraitement et de régression.
- `ml/artifacts/model_metadata.json` : contrat d'entrée, version et empreinte de l'artefact.
- `ml/artifacts/metrics.json` : métriques de référence, protocole d'évaluation et audit des données.

Les anciens fichiers `model.pkl`, `scaler.pkl`, `feature_columns.pkl`,
`quartier_freq.pkl` et `mode_par_ville.pkl` sont conservés pour la traçabilité.
Le travail ML reproductible se trouve dans `ml/notebooks/model_final.ipynb` et son
audit est résumé dans `docs/ML_AUDIT.md`.

Le script de collecte peut être lancé depuis la racine avec :

```bash
python ml/src/data.py
```

Il écrit le jeu de données dans `data/raw/maisonlux_maroc_complet.csv`.

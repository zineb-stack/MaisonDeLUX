# MaisonLux Maroc — Backend Django

Backend Django + Django REST Framework qui sert le modele Random Forest
entraine sur les donnees reelles, avec base de donnees (utilisateurs,
historique des estimations) et panel d'administration integre.

## Installation

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:5000
```

Le serveur tourne sur `http://localhost:5000`.

## Compte administrateur

Un superuser a deja ete cree :
- **Utilisateur** : `admin`
- **Mot de passe** : `admin12345`

Panel d'administration : `http://localhost:5000/admin/`
(changez ce mot de passe avant toute mise en ligne publique)

Depuis l'admin, vous pouvez voir/modifier :
- **Users** (comptes crees via signup, mots de passe hashes)
- **Profiles** (telephone, role acheteur/promoteur)
- **Estimations** (historique de toutes les estimations effectuees)

## Endpoints API

| Endpoint | Methode | Description |
|---|---|---|
| `/` | GET | Statut de l'API |
| `/api/villes/` | GET | Liste des villes disponibles |
| `/api/metrics/` | GET | Metriques du modele (R², RMSE, MAE) |
| `/api/predict/` | POST | Estimation de prix (et sauvegarde en base) |
| `/api/signup/` | POST | Creation de compte |
| `/api/login/` | POST | Connexion |

## Structure

```
maisonlux_backend/     # Configuration Django (settings, urls)
api/                   # App principale (models, views, admin)
ml_model/               # Modele entraine (model.pkl, scaler.pkl, etc.)
db.sqlite3              # Base de donnees (creee apres migrate)
manage.py
requirements.txt
```

## Note sur la taille du modele

`model.pkl` est compresse (~47 Mo) pour rester compatible avec GitHub
(limite de 100 Mo par fichier). Les predictions sont identiques a la
version non compressee.

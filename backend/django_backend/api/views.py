import re
from django.contrib.auth.models import User
from django.contrib.auth.hashers import check_password
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from .models import Profile, Estimation
from . import ml_utils

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@api_view(["GET"])
def index(request):
    return Response({
        "status": "ok",
        "message": "API MaisonLux Maroc — Django + Random Forest",
        "endpoints": [
            "/api/predict/ (POST)", "/api/villes/ (GET)", "/api/metrics/ (GET)",
            "/api/signup/ (POST)", "/api/login/ (POST)",
        ],
    })


@api_view(["GET"])
def get_villes(request):
    return Response({"villes": ml_utils.villes_disponibles})


@api_view(["GET"])
def get_metrics(request):
    return Response(ml_utils.metrics)


@api_view(["POST"])
def predict(request):
    data = request.data
    ville = data.get("ville", "")
    quartier = (data.get("quartier") or "").strip()
    type_bien = data.get("type_bien", "appartement")
    try:
        surface = float(data.get("surface", 0))
        pieces = float(data.get("pieces", 1))
        chambres = float(data.get("chambres", 1))
        salles_bain = float(data.get("salles_bain", 1))
    except (TypeError, ValueError):
        return Response({"error": "Valeurs numériques invalides."}, status=status.HTTP_400_BAD_REQUEST)

    if surface <= 0:
        return Response({"error": "La surface doit être supérieure à 0."}, status=status.HTTP_400_BAD_REQUEST)

    result = ml_utils.predict_price(ville, quartier, type_bien, surface, pieces, chambres, salles_bain)
    result["ville"] = ville
    result["quartier"] = quartier if quartier else "Non renseigné"

    # Historique : on enregistre l'estimation (utilisateur anonyme ou connecté via user_id optionnel)
    user_id = data.get("user_id")
    user_obj = User.objects.filter(id=user_id).first() if user_id else None
    Estimation.objects.create(
        user=user_obj, ville=ville, quartier=quartier, type_bien=type_bien,
        surface=surface, pieces=pieces, chambres=chambres, salles_bain=salles_bain,
        prix_estime=result["prix_estime"], prix_min=result["prix_min"], prix_max=result["prix_max"],
    )

    return Response(result)


@api_view(["POST"])
def signup(request):
    data = request.data
    prenom = (data.get("prenom") or "").strip()
    nom = (data.get("nom") or "").strip()
    email = (data.get("email") or "").strip().lower()
    telephone = (data.get("telephone") or "").strip()
    password = data.get("password") or ""
    role = data.get("role") or "acheteur"

    if not prenom or not nom or not email or not password:
        return Response({"error": "Tous les champs obligatoires doivent être remplis."}, status=status.HTTP_400_BAD_REQUEST)
    if not EMAIL_RE.match(email):
        return Response({"error": "Adresse email invalide."}, status=status.HTTP_400_BAD_REQUEST)
    if len(password) < 8:
        return Response({"error": "Le mot de passe doit contenir au moins 8 caractères."}, status=status.HTTP_400_BAD_REQUEST)
    if role not in ("acheteur", "promoteur"):
        role = "acheteur"

    if User.objects.filter(email=email).exists():
        return Response({"error": "Un compte existe déjà avec cet email."}, status=status.HTTP_409_CONFLICT)

    user = User.objects.create_user(username=email, email=email, password=password,
                                     first_name=prenom, last_name=nom)
    Profile.objects.create(user=user, telephone=telephone, role=role)

    return Response({
        "message": "Compte créé avec succès.",
        "user_id": user.id,
        "prenom": prenom,
        "email": email,
        "role": role,
    }, status=status.HTTP_201_CREATED)


@api_view(["POST"])
def login_view(request):
    data = request.data
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return Response({"error": "Merci de remplir tous les champs."}, status=status.HTTP_400_BAD_REQUEST)

    user = User.objects.filter(email=email).first()
    if user is None or not check_password(password, user.password):
        return Response({"error": "Email ou mot de passe incorrect."}, status=status.HTTP_401_UNAUTHORIZED)

    profile = getattr(user, "profile", None)
    return Response({
        "message": "Connexion réussie.",
        "user_id": user.id,
        "prenom": user.first_name,
        "nom": user.last_name,
        "email": user.email,
        "role": profile.role if profile else "acheteur",
    })

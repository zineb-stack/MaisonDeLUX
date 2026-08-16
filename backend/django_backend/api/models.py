from django.db import models
from django.contrib.auth.models import User


class Profile(models.Model):
    ROLE_CHOICES = [
        ("acheteur", "Acheteur"),
        ("promoteur", "Promoteur"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    telephone = models.CharField(max_length=30, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="acheteur")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.first_name} {self.user.last_name} ({self.user.email})"


class Estimation(models.Model):
    """Historique des estimations effectuees (utilisateur connecte, ou anonyme)."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="estimations", null=True, blank=True)
    ville = models.CharField(max_length=100)
    quartier = models.CharField(max_length=150, blank=True)
    type_bien = models.CharField(max_length=50)
    surface = models.FloatField()
    pieces = models.FloatField()
    chambres = models.FloatField()
    salles_bain = models.FloatField()
    prix_estime = models.FloatField()
    prix_min = models.FloatField()
    prix_max = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.ville} - {self.surface}m2 - {self.prix_estime:.0f} DH"

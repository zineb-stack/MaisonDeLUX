from django.contrib import admin
from .models import Profile, Estimation


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "telephone", "created_at")
    list_filter = ("role",)
    search_fields = ("user__email", "user__first_name", "user__last_name")


@admin.register(Estimation)
class EstimationAdmin(admin.ModelAdmin):
    list_display = ("ville", "quartier", "type_bien", "surface", "prix_estime", "user", "created_at")
    list_filter = ("ville", "type_bien")
    search_fields = ("ville", "quartier")

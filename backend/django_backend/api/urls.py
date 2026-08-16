from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("api/villes/", views.get_villes, name="get_villes"),
    path("api/metrics/", views.get_metrics, name="get_metrics"),
    path("api/predict/", views.predict, name="predict"),
    path("api/signup/", views.signup, name="signup"),
    path("api/login/", views.login_view, name="login"),
]

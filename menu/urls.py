from django.urls import path
from . import views

app_name = "menu"

urlpatterns = [
    path("", views.home, name="home"),
    path("inscription/", views.inscription, name="inscription"),
    path("connexion/", views.connexion, name="connexion"),
    path("deconnexion/", views.deconnexion, name="deconnexion"),
    path("famille/inviter/<uuid:token>/", views.rejoindre_famille, name="rejoindre_famille"),
    path("famille/rejoindre/", views.rejoindre_famille_page, name="rejoindre_famille_page"),
    path("planning/", views.planning, name="planning"),
]

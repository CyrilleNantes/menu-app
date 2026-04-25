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
    path("planning/<int:year>/<int:week>/", views.planning_semaine, name="planning_semaine"),
    path("planning/<int:plan_id>/meal/", views.modifier_meal, name="modifier_meal"),
    path("planning/<int:plan_id>/publier/", views.publier_planning, name="publier_planning"),
    path("planning/<int:plan_id>/proposer/", views.proposer_repas, name="proposer_repas"),
    path("api/recettes/", views.api_recettes, name="api_recettes"),
    path("recettes/", views.liste_recettes, name="liste_recettes"),
    path("recettes/<int:id>/", views.detail_recette, name="detail_recette"),
    path("recettes/<int:id>/cuisine/", views.mode_cuisine, name="mode_cuisine"),
    path("api/ingredients/nutrition/", views.recherche_nutrition, name="recherche_nutrition"),
    path("recettes/creer/", views.creer_recette, name="creer_recette"),
    path("recettes/<int:id>/modifier/", views.modifier_recette, name="modifier_recette"),
    path("recettes/<int:id>/supprimer/", views.supprimer_recette, name="supprimer_recette"),
    # Backup / Restore / Import recettes
    path("backup/", views.backup_page, name="backup_page"),
    path("backup/export/", views.export_backup, name="export_backup"),
    path("backup/importer/", views.import_backup, name="import_backup"),
    path("backup/recettes/importer/", views.import_recettes, name="import_recettes"),
]

from django.urls import path
from . import views

app_name = "menu"

urlpatterns = [
    path("sw.js", views.service_worker, name="service_worker"),
    path("profil/", views.profil, name="profil"),
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
    path("planning/<int:plan_id>/suggestions/", views.suggestions_repas, name="suggestions_repas"),
    path("planning/<int:plan_id>/bilan/", views.bilan_planning_ajax, name="bilan_planning_ajax"),
    path("planning/proposition/<int:proposal_id>/supprimer/", views.supprimer_proposition, name="supprimer_proposition"),
    path("api/recettes/", views.api_recettes, name="api_recettes"),
    path("api/ingredients/ciqual/", views.recherche_ciqual, name="recherche_ciqual"),
    path("api/ingredients/<int:ingredient_id>/set-ciqual/", views.set_ciqual_ingredient, name="set_ciqual_ingredient"),
    path("courses/<int:plan_id>/", views.liste_courses, name="liste_courses"),
    path("courses/generer/<int:plan_id>/", views.generer_courses, name="generer_courses"),
    path("courses/item/<int:id>/cocher/", views.cocher_item, name="cocher_item"),
    path("recettes/", views.liste_recettes, name="liste_recettes"),
    path("recettes/ciqual-audit/", views.audit_ciqual, name="audit_ciqual"),
    path("recettes/<int:id>/", views.detail_recette, name="detail_recette"),
    path("recettes/<int:id>/cuisine/", views.mode_cuisine, name="mode_cuisine"),
    path("recettes/<int:id>/noter/", views.noter_recette, name="noter_recette"),
    path("recettes/creer/", views.creer_recette, name="creer_recette"),
    path("recettes/<int:id>/modifier/", views.modifier_recette, name="modifier_recette"),
    path("recettes/<int:id>/supprimer/", views.supprimer_recette, name="supprimer_recette"),
    # Galerie photos
    path("recettes/<int:id>/photos/ajouter/", views.ajouter_photo_recette, name="ajouter_photo_recette"),
    path("recettes/<int:id>/photos/<int:photo_id>/retirer/", views.retirer_photo_recette, name="retirer_photo_recette"),
    path("recettes/<int:id>/photos/<int:photo_id>/promouvoir/", views.promouvoir_photo_recette, name="promouvoir_photo_recette"),
    # Google Calendar
    path("planning/<int:plan_id>/export-calendar/", views.export_calendar, name="export_calendar"),
    path("profil/nutrition/", views.dashboard_nutrition, name="dashboard_nutrition"),
    path("profil/creneaux-calendar/", views.modifier_creneaux_calendar, name="modifier_creneaux_calendar"),
    path("profil/portions-factor/", views.modifier_portions_factor, name="modifier_portions_factor"),
    path("profil/dietary-tags/", views.modifier_dietary_tags, name="modifier_dietary_tags"),
    path("recettes/<int:id>/compatibilite/", views.compatibilite_recette, name="compatibilite_recette"),
    # Google Tasks
    path("courses/<int:plan_id>/export-tasks/", views.export_tasks, name="export_tasks"),
    # OAuth Google
    path("google/connect/", views.google_connect, name="google_connect"),
    path("google/callback/", views.google_callback, name="google_callback"),
    path("google/disconnect/", views.google_disconnect, name="google_disconnect"),
    # Backup / Restore / Import recettes
    path("backup/", views.backup_page, name="backup_page"),
    path("backup/export/", views.export_backup, name="export_backup"),
    path("backup/importer/", views.import_backup, name="import_backup"),
    path("backup/recettes/importer/", views.import_recettes, name="import_recettes"),
]

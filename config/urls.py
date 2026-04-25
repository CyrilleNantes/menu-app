from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("menu.urls")),
    # allauth.urls sera activé à l'étape 14 (Google OAuth)
    # path("accounts/", include("allauth.urls")),
]

from dotenv import load_dotenv
from pathlib import Path
import dj_database_url
import os

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# =========================================================
# 🔐 SECURITY
# =========================================================

SECRET_KEY = os.getenv("SECRET_KEY", "fallback-insecure-key")

DEBUG = os.getenv("DEBUG", "False") == "True"

# "dev" sur Railway dev, absent (= production) sinon
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")
IS_DEV = ENVIRONMENT == "dev"

# Domaine Railway (injecté automatiquement)
RAILWAY_DOMAIN = os.getenv("RAILWAY_PUBLIC_DOMAIN")

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "menu-app-dev.up.railway.app",
    "menu-app-production-0c67.up.railway.app",
]

if RAILWAY_DOMAIN:
    ALLOWED_HOSTS.append(RAILWAY_DOMAIN)

# =========================================================
# 📦 APPLICATIONS
# =========================================================

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    # allauth (OAuth Google activé à l'étape 14)
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    # app principale
    "menu",
]

SITE_ID = 1

# =========================================================
# ⚙️ MIDDLEWARE
# =========================================================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "config.urls"

# =========================================================
# 🎨 TEMPLATES
# =========================================================

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "menu.context_processors.environment",  # 🔥 à créer
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "menu:connexion"
LOGIN_REDIRECT_URL = "menu:home"
LOGOUT_REDIRECT_URL = "menu:connexion"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]

# django-allauth (activé à l'étape 14 — Google OAuth)
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]

# =========================================================
# 🗄️ DATABASE (Railway PostgreSQL)
# =========================================================

DATABASES = {
    "default": dj_database_url.config(
        conn_max_age=600,
    )
}

# =========================================================
# 🔑 PASSWORD VALIDATION
# =========================================================

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# =========================================================
# 🌍 INTERNATIONALISATION
# =========================================================

LANGUAGE_CODE = "fr"
TIME_ZONE = "Europe/Paris"

USE_I18N = True
USE_TZ = True

# =========================================================
# 📁 STATIC FILES
# =========================================================

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

WHITENOISE_KEEP_ONLY_HASHED_FILES = False

# =========================================================
# 🔒 CONFIG PROD (Railway / HTTPS / CSRF)
# =========================================================

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

CSRF_TRUSTED_ORIGINS = [
    f"https://{host}"
    for host in ALLOWED_HOSTS
    if host not in {"localhost", "127.0.0.1"}
]

CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG

CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_HTTPONLY = True

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True

# =========================================================
# 📋 LOGGING
# =========================================================

# =========================================================
# 🔑 AUTHENTIFICATION (django-allauth)
# =========================================================

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_USERNAME_REQUIRED = False

LOGIN_REDIRECT_URL = "/"
ACCOUNT_LOGOUT_REDIRECT_URL = "/connexion/"
LOGIN_URL = "/connexion/"

# =========================================================
# 📧 EMAIL (SMTP via Railway)
# =========================================================

_email_host_user = os.getenv("EMAIL_HOST_USER", "")

if _email_host_user:
    # Config SMTP réelle (prod / dev Railway)
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
    EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
    EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True") == "True"
    EMAIL_HOST_USER = _email_host_user
    EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
else:
    # Fallback local : affiche les emails dans la console
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    EMAIL_HOST_USER = ""
    EMAIL_HOST_PASSWORD = ""

DEFAULT_FROM_EMAIL = os.getenv(
    "DEFAULT_FROM_EMAIL",
    f"Menu Familial <{_email_host_user}>" if _email_host_user else "Menu Familial <noreply@menu-familial.app>",
)

# =========================================================
# 📋 LOGGING
# =========================================================

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} — {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "menu": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
    },
}
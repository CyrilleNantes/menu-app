from django import forms
from django.contrib.auth.models import User

from .models import Recipe


class InscriptionForm(forms.Form):
    prenom = forms.CharField(max_length=50, label="Prénom")
    nom = forms.CharField(max_length=50, label="Nom")
    email = forms.EmailField(label="Email")
    password1 = forms.CharField(widget=forms.PasswordInput, label="Mot de passe")
    password2 = forms.CharField(widget=forms.PasswordInput, label="Confirmer le mot de passe")
    role = forms.ChoiceField(
        choices=[("cuisinier", "Cuisinier — je crée ma famille"), ("convive", "Convive — je rejoindrai via invitation")],
        widget=forms.RadioSelect,
        label="Mon rôle",
    )
    nom_famille = forms.CharField(max_length=100, label="Nom de la famille", required=False,
                                   help_text="Requis si vous êtes Cuisinier")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password1") != cleaned.get("password2"):
            raise forms.ValidationError("Les mots de passe ne correspondent pas.")
        if cleaned.get("role") == "cuisinier" and not cleaned.get("nom_famille"):
            raise forms.ValidationError("Un nom de famille est requis pour le Cuisinier.")
        if User.objects.filter(email=cleaned.get("email", "")).exists():
            raise forms.ValidationError("Cet email est déjà utilisé.")
        return cleaned


SAISON_CHOICES = [
    ("printemps", "Printemps"), ("ete", "Été"), ("automne", "Automne"), ("hiver", "Hiver"),
]
HEALTH_CHOICES = [
    ("leger", "Léger"), ("equilibre", "Équilibré"), ("plaisir", "Plaisir raisonné"),
    ("proteine", "Protéiné"), ("vegetarien", "Végétarien"), ("vegan", "Végétalien"),
]


class RecipeForm(forms.Form):
    title = forms.CharField(max_length=200, label="Titre")
    description = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 2}), label="Description courte"
    )
    photo = forms.ImageField(required=False, label="Photo du plat")
    base_servings = forms.IntegerField(min_value=1, label="Nombre de parts")
    prep_time = forms.IntegerField(required=False, min_value=0, label="Préparation (min)")
    cook_time = forms.IntegerField(required=False, min_value=0, label="Cuisson (min)")
    category = forms.ChoiceField(choices=Recipe.CATEGORY_CHOICES, label="Catégorie")
    cuisine_type = forms.CharField(required=False, max_length=50, label="Type de cuisine")
    complexity = forms.ChoiceField(choices=Recipe.COMPLEXITY_CHOICES, label="Complexité")
    seasons = forms.MultipleChoiceField(
        required=False, choices=SAISON_CHOICES,
        widget=forms.CheckboxSelectMultiple, label="Saisons",
    )
    health_tags = forms.MultipleChoiceField(
        required=False, choices=HEALTH_CHOICES,
        widget=forms.CheckboxSelectMultiple, label="Tags santé",
    )

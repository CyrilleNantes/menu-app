from django import forms
from django.contrib.auth.models import User


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

"""email.py — envoi d'emails transactionnels (notifications Menu Familial)."""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger("menu")


def envoyer_email(
    subject: str,
    template_txt: str,
    template_html: str,
    context: dict,
    recipients: list,
) -> int:
    """
    Envoie un email HTML + texte à une liste de destinataires.

    Retourne le nombre de messages envoyés (0 si échec ou liste vide).
    Les erreurs sont loggées et avalées pour ne jamais faire planter la vue.
    """
    if not recipients:
        return 0

    try:
        text_content = render_to_string(template_txt, context)
        html_content = render_to_string(template_html, context)

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients,
        )
        msg.attach_alternative(html_content, "text/html")
        sent = msg.send(fail_silently=False)
        logger.info("Email '%s' envoyé à %d destinataire(s).", subject, len(recipients))
        return sent

    except Exception as exc:  # noqa: BLE001
        logger.error("Erreur envoi email '%s' : %s", subject, exc)
        return 0

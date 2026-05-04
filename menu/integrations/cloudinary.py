import logging
import os

import cloudinary
import cloudinary.uploader

logger = logging.getLogger("menu")


def upload_photo(file) -> str | None:
    """Upload une photo vers Cloudinary et retourne l'URL sécurisée, ou None si échec/non configuré."""
    if not os.environ.get("CLOUDINARY_URL"):
        logger.debug("CLOUDINARY_URL non défini — upload ignoré.")
        return None
    try:
        result = cloudinary.uploader.upload(
            file,
            folder="menu_familial",
            allowed_formats=["jpg", "jpeg", "png", "webp"],
        )
        return result["secure_url"]
    except Exception as exc:
        logger.error("Cloudinary upload failed : %s", exc)
        return None

from django import template

register = template.Library()

_CLOUDINARY_PRESETS = {
    "card":    "f_auto,q_auto,w_600,c_limit",
    "header":  "f_auto,q_auto,w_1200,c_limit",
    "gallery": "f_auto,q_auto,w_900,c_limit",
    "thumb":   "f_auto,q_auto,w_300,c_limit",
}


@register.filter
def cloudinary_img(url, preset="gallery"):
    """Insère des paramètres de transformation Cloudinary dans l'URL pour optimiser l'affichage.

    Usage : {{ photo.photo_url|cloudinary_img:"gallery" }}
    Presets : card (600px), header (1200px), gallery (900px), thumb (300px).
    """
    if not url or "/upload/" not in url:
        return url or ""
    params = _CLOUDINARY_PRESETS.get(preset, preset)
    return url.replace("/upload/", f"/upload/{params}/", 1)


@register.filter
def format_timer(seconds):
    if not seconds:
        return ""
    if seconds < 60:
        return f"{seconds} sec"
    mins = seconds // 60
    secs = seconds % 60
    if secs:
        return f"{mins} min {secs:02d}"
    return f"{mins} min"

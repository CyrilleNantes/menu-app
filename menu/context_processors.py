def environment(request):
    from django.conf import settings
    ctx = {"IS_DEV": settings.IS_DEV}

    if request.user.is_authenticated:
        try:
            profile = request.user.profile
            ctx["user_rank"] = profile.rank
            ctx["user_is_cuisinier"] = profile.role in ("cuisinier", "chef_etoile")
        except Exception:
            ctx["user_rank"] = (0, "")
            ctx["user_is_cuisinier"] = False

    return ctx
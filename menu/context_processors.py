def environment(request):
    from django.conf import settings
    ctx = {"IS_DEV": settings.IS_DEV}

    if request.user.is_authenticated:
        try:
            ctx["user_rank"] = request.user.profile.rank
        except Exception:
            ctx["user_rank"] = (0, "")

    return ctx
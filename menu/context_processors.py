def environment(request):
    from django.conf import settings
    return {
        "IS_DEV": settings.IS_DEV
    }
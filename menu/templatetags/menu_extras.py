from django import template

register = template.Library()


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

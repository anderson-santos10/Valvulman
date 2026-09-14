from django.template import Library

register = Library()


@register.simple_tag(takes_context=True)
def vm_qs(context, **kwargs):
    request = context.get("request")
    if request is None:
        return "?"
    query = request.GET.copy()
    for key, value in kwargs.items():
        if value in (None, ""):
            query.pop(key, None)
        else:
            query[key] = value
    encoded = query.urlencode()
    return "?{0}".format(encoded) if encoded else "?"

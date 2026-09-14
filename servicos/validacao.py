import base64
from io import BytesIO

from django.conf import settings
from django.urls import reverse


def url_validacao_publica(token, request=None):
    caminho = reverse("validar_certificado", args=[token])
    base = (getattr(settings, "PUBLIC_BASE_URL", "") or "").rstrip("/")
    if base:
        return f"{base}{caminho}"
    if request is not None:
        return request.build_absolute_uri(caminho)
    if settings.DEBUG:
        return f"http://127.0.0.1:8000{caminho}"
    return caminho


def qr_code_data_uri(url):
    import segno

    qr = segno.make(url, error="m")
    buffer = BytesIO()
    qr.save(buffer, kind="svg", xmldecl=False, svgns=True, scale=4, border=1)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"

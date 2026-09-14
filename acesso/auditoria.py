import logging

from .models import RegistroAuditoria

logger = logging.getLogger(__name__)


def obter_ip_cliente(request):
    if request is None:
        return None
    return request.META.get("REMOTE_ADDR") or None


def registrar_auditoria(
    *,
    acao,
    objeto=None,
    descricao="",
    request=None,
    usuario=None,
    modelo=None,
    objeto_id=None,
):
    if usuario is None and request is not None and getattr(
        request.user, "is_authenticated", False
    ):
        usuario = request.user
    if objeto is not None:
        modelo = modelo or objeto.__class__.__name__
        if objeto_id is None:
            objeto_id = getattr(objeto, "numero", None) or getattr(objeto, "pk", "")
    modelo = modelo or ""
    objeto_id = "" if objeto_id is None else str(objeto_id)
    ip = obter_ip_cliente(request)
    if usuario is not None and not getattr(usuario, "is_authenticated", True):
        usuario = None
    try:
        RegistroAuditoria.objects.create(
            usuario=usuario,
            acao=acao,
            modelo=modelo,
            objeto_id=objeto_id,
            descricao=descricao or "",
            ip=ip,
        )
    except Exception:
        logger.exception("Falha ao gravar auditoria %s", acao)

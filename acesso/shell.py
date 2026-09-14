"""Apresentação do usuário no shell. Não altera permissões."""

from acesso.permissoes import GRUPOS

ROTULOS_GRUPO = {
    "ADMINISTRADOR": "Administrador",
    "TECNICO": "Técnico",
    "COMERCIAL": "Comercial",
    "FINANCEIRO": "Financeiro",
    "CONSULTA": "Consulta",
}


def cargo_shell(user):
    """Grupo de maior prioridade em GRUPOS; superusuário sem grupo → Administrador."""
    if user is None or not getattr(user, "is_authenticated", False):
        return ""
    nomes = set(user.groups.values_list("name", flat=True))
    for nome in GRUPOS:
        if nome in nomes:
            return ROTULOS_GRUPO.get(nome, nome)
    extra = user.groups.order_by("name").values_list("name", flat=True).first()
    if extra:
        return ROTULOS_GRUPO.get(extra, extra)
    if user.is_superuser:
        return ROTULOS_GRUPO["ADMINISTRADOR"]
    return ""

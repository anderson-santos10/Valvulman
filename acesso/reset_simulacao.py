"""Catálogo e execução do reset de dados de simulação.

Não usa flush, não apaga o arquivo do banco e não altera o schema.
"""

from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import ForeignKey, OneToOneField

from acesso.models import RegistroAuditoria
from clientes.models import Cliente
from servicos.models import (
    Calibracao,
    CertificadoCalibracao,
    Cobranca,
    ExecucaoValvula,
    Instrumento,
    ItemOrcamento,
    ItemOrdemServico,
    Orcamento,
    OrdemServico,
    PadraoMedicao,
    Pagamento,
    PontoCalibracao,
    RelatorioTecnico,
    Valvula,
    ValvulaRelatorio,
)

CONFIRMACAO_RESET = "RESETAR"

# Histórico de operações. Não é autenticação; após o reset os registros
# apontariam para OS/clientes inexistentes.
MODELOS_NEGOCIO = (
    Pagamento,
    PontoCalibracao,
    CertificadoCalibracao,
    ExecucaoValvula,
    Calibracao,
    ItemOrdemServico,
    ItemOrcamento,
    Cobranca,
    OrdemServico,
    ValvulaRelatorio,
    RelatorioTecnico,
    Orcamento,
    Valvula,
    Instrumento,
    PadraoMedicao,
    Cliente,
    RegistroAuditoria,
)

MODELOS_PRESERVADOS = (
    User,
    Group,
    Permission,
    ContentType,
)

CONTADORES_FOTOGRAFIA = (
    ("Clientes", Cliente),
    ("Válvulas", Valvula),
    ("Instrumentos", Instrumento),
    ("Padrões de medição", PadraoMedicao),
    ("Ordens de Serviço", OrdemServico),
    ("Itens de OS", ItemOrdemServico),
    ("Calibrações", Calibracao),
    ("Pontos de calibração", PontoCalibracao),
    ("Execuções de válvula", ExecucaoValvula),
    ("Certificados", CertificadoCalibracao),
    ("Orçamentos", Orcamento),
    ("Itens de orçamento", ItemOrcamento),
    ("Relatórios técnicos", RelatorioTecnico),
    ("Linhas de relatório", ValvulaRelatorio),
    ("Cobranças", Cobranca),
    ("Pagamentos", Pagamento),
    ("Registros de auditoria", RegistroAuditoria),
)


def _fk_para_negocio(modelo, conjunto):
    alvos = []
    for campo in modelo._meta.get_fields():
        if not isinstance(campo, (ForeignKey, OneToOneField)):
            continue
        relacionado = campo.remote_field.model
        if relacionado in conjunto and relacionado is not modelo:
            alvos.append(relacionado)
    return alvos


def ordem_exclusao(modelos=MODELOS_NEGOCIO):
    """Dependentes primeiro (quem aponta para outro model sai antes), para respeitar PROTECT."""
    pendentes = list(modelos)
    conjunto = set(pendentes)
    apontam_para = {modelo: [] for modelo in pendentes}
    for modelo in pendentes:
        for alvo in _fk_para_negocio(modelo, conjunto):
            apontam_para[alvo].append(modelo)
    ordenados = []
    while pendentes:
        liberados = [
            modelo
            for modelo in pendentes
            if not any(origem in pendentes for origem in apontam_para[modelo])
        ]
        if not liberados:
            ordenados.extend(pendentes)
            break
        for modelo in liberados:
            ordenados.append(modelo)
            pendentes.remove(modelo)
    return ordenados


def fotografia_negocio():
    return [(rotulo, modelo.objects.count()) for rotulo, modelo in CONTADORES_FOTOGRAFIA]


def fotografia_acesso():
    return {
        "usuarios": User.objects.count(),
        "grupos": Group.objects.count(),
        "permissoes": Permission.objects.count(),
        "content_types": ContentType.objects.count(),
    }


def apagar_dados_negocio():
    """Apaga só dados de negócio. QuerySet.delete evita Pagamento/Cobranca.delete()."""
    acesso_antes = fotografia_acesso()
    total = 0
    detalhes = []
    with transaction.atomic():
        for modelo in ordem_exclusao():
            quantidade, _ = modelo.objects.all().delete()
            total += quantidade
            detalhes.append((modelo._meta.label, quantidade))
        for modelo in MODELOS_NEGOCIO:
            if modelo.objects.exists():
                raise RuntimeError(
                    f"Reset incompleto: {modelo._meta.label} ainda possui registros."
                )
        acesso_depois = fotografia_acesso()
        if acesso_depois != acesso_antes:
            raise RuntimeError(
                "Reset abortado: usuários, grupos ou permissões foram alterados."
            )
    return total, detalhes

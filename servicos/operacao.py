from datetime import datetime
from decimal import Decimal

from django.db.models import (
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import (
    Calibracao,
    Cobranca,
    Instrumento,
    ItemOrdemServico,
    Orcamento,
    OrdemServico,
    Pagamento,
    ResultadoCalibracao,
    StatusCalibracao,
    StatusCobranca,
    StatusItemOrdem,
    StatusOrcamento,
    StatusOrdemServico,
)


def _parse_data(valor):
    texto = (valor or "").strip()
    if not texto:
        return None
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date()
    except ValueError:
        return None


def queryset_ordens_atrasadas(queryset=None, hoje=None):
    hoje = hoje or timezone.localdate()
    qs = queryset if queryset is not None else OrdemServico.objects.all()
    return qs.filter(data_previsao_entrega__lt=hoje).exclude(
        status__in=(
            StatusOrdemServico.ENTREGUE,
            StatusOrdemServico.CANCELADA,
        )
    )


def queryset_instrumentos_vencidos(hoje=None):
    hoje = hoje or timezone.localdate()
    ultima_validade = (
        Calibracao.objects.filter(instrumento_id=OuterRef("pk"))
        .exclude(status=StatusCalibracao.CANCELADA)
        .order_by("-data_calibracao", "-pk")
        .values("data_validade")[:1]
    )
    return (
        Instrumento.objects.filter(ativo=True)
        .annotate(_ultima_validade=Subquery(ultima_validade))
        .filter(_ultima_validade__lt=hoje)
    )


def aplicar_filtros_lista_ordens(queryset, params, hoje=None):
    hoje = hoje or timezone.localdate()
    pesquisa = (params.get("q") or "").strip()
    if pesquisa:
        queryset = queryset.filter(
            Q(numero__icontains=pesquisa)
            | Q(cliente__nome__icontains=pesquisa)
            | Q(cliente__cnpj__icontains=pesquisa)
            | Q(solicitante__icontains=pesquisa)
            | Q(itens__instrumento__codigo__icontains=pesquisa)
            | Q(itens__instrumento__tag__icontains=pesquisa)
            | Q(itens__instrumento__numero_serie__icontains=pesquisa)
            | Q(itens__valvula__codigo__icontains=pesquisa)
            | Q(itens__valvula__tag__icontains=pesquisa)
            | Q(itens__valvula__numero_serie__icontains=pesquisa)
        ).distinct()
    status = (params.get("status") or "").strip()
    if status:
        queryset = queryset.filter(status=status)
    cliente_id = (params.get("cliente") or "").strip()
    if cliente_id.isdigit():
        queryset = queryset.filter(cliente_id=int(cliente_id))
    data_de = _parse_data(params.get("data_de"))
    data_ate = _parse_data(params.get("data_ate"))
    if data_de:
        queryset = queryset.filter(data_entrada__gte=data_de)
    if data_ate:
        queryset = queryset.filter(data_entrada__lte=data_ate)
    atrasadas = (params.get("atrasadas") or "").strip()
    if atrasadas in ("1", "on", "true", "sim"):
        queryset = queryset_ordens_atrasadas(queryset, hoje=hoje)
    return queryset


def _decimal_zero():
    return Value(Decimal("0.00"), output_field=DecimalField(max_digits=12, decimal_places=2))


def queryset_cobrancas_anotadas():
    pago = (
        Pagamento.objects.filter(cobranca_id=OuterRef("pk"))
        .values("cobranca")
        .annotate(total=Sum("valor"))
        .values("total")
    )
    saldo = ExpressionWrapper(
        F("valor_final") - F("total_pago_agg"),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )
    return (
        Cobranca.objects.select_related("cliente", "orcamento", "ordem_servico")
        .annotate(
            total_pago_agg=Coalesce(Subquery(pago), _decimal_zero()),
            qtd_pagamentos=Count("pagamentos", distinct=True),
        )
        .annotate(saldo_agg=saldo)
    )


def queryset_cobrancas_em_aberto(queryset=None):
    qs = queryset if queryset is not None else queryset_cobrancas_anotadas()
    return qs.exclude(status=StatusCobranca.CANCELADO).filter(saldo_agg__gt=0)


def queryset_cobrancas_vencidas(queryset=None, hoje=None):
    hoje = hoje or timezone.localdate()
    return queryset_cobrancas_em_aberto(queryset).filter(data_vencimento__lt=hoje)


def queryset_cobrancas_a_vencer(queryset=None, hoje=None):
    hoje = hoje or timezone.localdate()
    return queryset_cobrancas_em_aberto(queryset).filter(data_vencimento__gte=hoje)


def totais_financeiro_cliente(cliente, hoje=None):
    hoje = hoje or timezone.localdate()
    qs = queryset_cobrancas_anotadas().filter(cliente=cliente)
    aberto = queryset_cobrancas_em_aberto(qs).aggregate(
        total=Coalesce(Sum("saldo_agg"), _decimal_zero())
    )["total"]
    vencido = queryset_cobrancas_vencidas(qs, hoje=hoje).aggregate(
        total=Coalesce(Sum("saldo_agg"), _decimal_zero())
    )["total"]
    pago = Pagamento.objects.filter(cobranca__cliente=cliente).aggregate(
        total=Coalesce(Sum("valor"), _decimal_zero())
    )["total"]
    return {
        "total_em_aberto": aberto or Decimal("0.00"),
        "total_vencido": vencido or Decimal("0.00"),
        "total_pago": pago or Decimal("0.00"),
    }


def aplicar_filtros_cobrancas(queryset, params, hoje=None):
    hoje = hoje or timezone.localdate()
    pesquisa = (params.get("q") or "").strip()
    if pesquisa:
        queryset = queryset.filter(
            Q(numero__icontains=pesquisa)
            | Q(cliente__nome__icontains=pesquisa)
            | Q(cliente__cnpj__icontains=pesquisa)
            | Q(ordem_servico__numero__icontains=pesquisa)
            | Q(orcamento__numero__icontains=pesquisa)
        ).distinct()
    cliente_id = (params.get("cliente") or "").strip()
    if cliente_id.isdigit():
        queryset = queryset.filter(cliente_id=int(cliente_id))
    forma = (params.get("forma_pagamento") or "").strip()
    if forma:
        queryset = queryset.filter(forma_pagamento=forma)
    data_de = _parse_data(params.get("data_de"))
    data_ate = _parse_data(params.get("data_ate"))
    if data_de:
        queryset = queryset.filter(data_emissao__gte=data_de)
    if data_ate:
        queryset = queryset.filter(data_emissao__lte=data_ate)
    vencidas = (params.get("vencidas") or "").strip()
    pagas = (params.get("pagas") or "").strip()
    status = (params.get("status") or "").strip()
    if vencidas in ("1", "on", "true", "sim") or status == StatusCobranca.VENCIDO:
        queryset = queryset_cobrancas_vencidas(queryset, hoje=hoje)
    elif pagas in ("1", "on", "true", "sim") or status == StatusCobranca.PAGO:
        queryset = queryset.exclude(status=StatusCobranca.CANCELADO).filter(
            saldo_agg__lte=0
        )
    elif status == StatusCobranca.PENDENTE:
        queryset = queryset.filter(
            status=StatusCobranca.PENDENTE,
            data_vencimento__gte=hoje,
            saldo_agg__gt=0,
        )
    elif status == StatusCobranca.PARCIAL:
        queryset = queryset.filter(
            status=StatusCobranca.PARCIAL,
            data_vencimento__gte=hoje,
            saldo_agg__gt=0,
        )
    elif status == StatusCobranca.CANCELADO:
        queryset = queryset.filter(status=StatusCobranca.CANCELADO)
    return queryset


def indicadores_financeiro(hoje=None):
    hoje = hoje or timezone.localdate()
    cobrancas = queryset_cobrancas_anotadas()
    aberto = queryset_cobrancas_em_aberto(cobrancas)
    vencidas = queryset_cobrancas_vencidas(cobrancas, hoje=hoje)
    a_vencer = queryset_cobrancas_a_vencer(cobrancas, hoje=hoje)
    recebido = Pagamento.objects.filter(
        data_pagamento__year=hoje.year,
        data_pagamento__month=hoje.month,
    ).aggregate(total=Coalesce(Sum("valor"), _decimal_zero()))["total"]
    return {
        "contas_a_receber": aberto.aggregate(
            total=Coalesce(Sum("saldo_agg"), _decimal_zero())
        )["total"]
        or Decimal("0.00"),
        "cobrancas_vencidas": vencidas.aggregate(
            total=Coalesce(Sum("saldo_agg"), _decimal_zero())
        )["total"]
        or Decimal("0.00"),
        "cobrancas_a_vencer": a_vencer.aggregate(
            total=Coalesce(Sum("saldo_agg"), _decimal_zero())
        )["total"]
        or Decimal("0.00"),
        "recebido_mes": recebido or Decimal("0.00"),
        "qtd_cobrancas_vencidas": vencidas.count(),
    }


def indicadores_operacao(hoje=None):
    hoje = hoje or timezone.localdate()
    ordens = OrdemServico.objects.all()
    calibracoes = Calibracao.objects.all()
    return {
        "os_abertas": ordens.filter(status=StatusOrdemServico.ABERTA).count(),
        "os_recebidas": ordens.filter(status=StatusOrdemServico.RECEBIDA).count(),
        "os_em_execucao": ordens.filter(status=StatusOrdemServico.EM_EXECUCAO).count(),
        "os_aguardando_revisao": ordens.filter(
            status=StatusOrdemServico.AGUARDANDO_REVISAO
        ).count(),
        "os_atrasadas": queryset_ordens_atrasadas(ordens, hoje=hoje).count(),
        "os_concluidas": ordens.filter(status=StatusOrdemServico.CONCLUIDA).count(),
        "os_entregues": ordens.filter(status=StatusOrdemServico.ENTREGUE).count(),
        "os_prontas_entrega": ordens.filter(
            status=StatusOrdemServico.CONCLUIDA
        ).count(),
        "calibracoes_concluidas": calibracoes.filter(
            status=StatusCalibracao.CONCLUIDA
        ).count(),
        "calibracoes_aprovadas": calibracoes.filter(
            resultado=ResultadoCalibracao.APROVADO
        ).count(),
        "calibracoes_reprovadas": calibracoes.filter(
            resultado=ResultadoCalibracao.REPROVADO
        ).count(),
        "instrumentos_vencidos": queryset_instrumentos_vencidos(hoje=hoje).count(),
        "orcamentos_rascunho": Orcamento.objects.filter(
            status=StatusOrcamento.RASCUNHO
        ).count(),
        "orcamentos_enviados": Orcamento.objects.filter(
            status=StatusOrcamento.ENVIADO
        ).count(),
        "orcamentos_aprovados": Orcamento.objects.filter(
            status=StatusOrcamento.APROVADO
        ).count(),
        "orcamentos_vencidos": Orcamento.objects.filter(
            status=StatusOrcamento.ENVIADO,
            data_validade__lt=hoje,
        ).count(),
        "valor_negociacao": Orcamento.objects.filter(
            status=StatusOrcamento.ENVIADO
        ).aggregate(
            total=Coalesce(
                Sum("itens__total"),
                Value(0, output_field=DecimalField(max_digits=12, decimal_places=2)),
            )
        )["total"],
        **indicadores_financeiro(hoje=hoje),
    }


def _base_fila():
    return OrdemServico.objects.select_related("cliente").annotate(
        total_itens=Count("itens")
    )


def fila_ordens():
    base = _base_fila()
    return {
        "aguardando_execucao": base.filter(
            status__in=(StatusOrdemServico.ABERTA, StatusOrdemServico.RECEBIDA)
        ).order_by("data_entrada", "data_previsao_entrega", "numero"),
        "em_execucao": base.filter(status=StatusOrdemServico.EM_EXECUCAO).order_by(
            "data_entrada", "data_previsao_entrega", "numero"
        ),
        "aguardando_revisao": base.filter(
            status=StatusOrdemServico.AGUARDANDO_REVISAO
        ).order_by("data_entrada", "data_previsao_entrega", "numero"),
        "prontas_entrega": base.filter(
            status=StatusOrdemServico.CONCLUIDA
        ).order_by("data_entrada", "data_previsao_entrega", "numero"),
        "entregues": base.filter(status=StatusOrdemServico.ENTREGUE).order_by(
            "-data_entrega", "-numero"
        ),
        "canceladas": base.filter(status=StatusOrdemServico.CANCELADA).order_by(
            "-atualizado_em", "-numero"
        ),
    }


def fila_itens():
    base = (
        ItemOrdemServico.objects.select_related(
            "ordem_servico",
            "ordem_servico__cliente",
            "instrumento",
            "valvula",
        )
        .exclude(
            ordem_servico__status__in=(
                StatusOrdemServico.ENTREGUE,
                StatusOrdemServico.CANCELADA,
            )
        )
        .exclude(status=StatusItemOrdem.CANCELADO)
    )
    return {
        "itens_recebidos": base.filter(status=StatusItemOrdem.RECEBIDO).order_by(
            "ordem_servico__data_entrada",
            "ordem_servico__numero",
            "pk",
        ),
        "itens_em_execucao": base.filter(status=StatusItemOrdem.EM_EXECUCAO).order_by(
            "ordem_servico__data_entrada",
            "ordem_servico__numero",
            "pk",
        ),
        "itens_aguardando_revisao": base.filter(
            status=StatusItemOrdem.AGUARDANDO_REVISAO
        ).order_by(
            "ordem_servico__data_entrada",
            "ordem_servico__numero",
            "pk",
        ),
    }


def historico_instrumento(instrumento):
    calibracoes = list(instrumento.calibracoes.all())
    itens = list(instrumento.itens_ordem_servico.all())
    eventos = []
    itens_com_calibracao = set()
    for calibracao in calibracoes:
        item = calibracao.item_ordem_servico
        ordem = item.ordem_servico if item else None
        if item:
            itens_com_calibracao.add(item.pk)
        eventos.append(
            {
                "data": calibracao.data_calibracao,
                "tipo": "calibracao",
                "calibracao": calibracao,
                "ordem": ordem,
                "certificado": calibracao.certificado_atual,
            }
        )
    for item in itens:
        if item.pk in itens_com_calibracao:
            continue
        eventos.append(
            {
                "data": item.ordem_servico.data_entrada,
                "tipo": "os",
                "calibracao": None,
                "ordem": item.ordem_servico,
                "certificado": None,
                "item": item,
            }
        )
    eventos.sort(key=lambda evento: (evento["data"], evento["tipo"]), reverse=True)
    certificados = []
    for calibracao in calibracoes:
        certificado = calibracao.certificado_atual
        if certificado:
            certificados.append(certificado)
    certificados.sort(key=lambda certificado: certificado.emitido_em, reverse=True)
    return {
        "eventos": eventos,
        "calibracoes": sorted(
            calibracoes,
            key=lambda calibracao: (calibracao.data_calibracao, calibracao.pk),
            reverse=True,
        ),
        "certificados": certificados,
        "ultima_calibracao": instrumento.ultima_calibracao(),
        "situacao_codigo": instrumento.situacao_calibracao_codigo,
        "situacao_rotulo": instrumento.situacao_calibracao_rotulo,
    }


def historico_valvula(valvula):
    itens = list(
        valvula.itens_ordem_servico.select_related(
            "ordem_servico",
            "execucao_valvula",
        ).all()
    )
    eventos = []
    for item in itens:
        execucao = item.execucao_valvula_atual
        eventos.append(
            {
                "data": item.ordem_servico.data_entrada,
                "tipo": "os",
                "ordem": item.ordem_servico,
                "item": item,
                "execucao": execucao,
                "resultado": execucao.get_resultado_display() if execucao else "",
            }
        )
    eventos.sort(key=lambda evento: (evento["data"], evento["ordem"].numero), reverse=True)
    return {"eventos_os": eventos}

"""Composição visual do dashboard a partir de indicadores já calculados."""

from decimal import Decimal

from django.urls import reverse


def _positivo(valor):
    if valor is None:
        return False
    return valor > 0


def _percentual(valor, maximo):
    if not _positivo(valor) or not _positivo(maximo):
        return 0
    percentual = int(round(100 * float(valor) / float(maximo)))
    if percentual < 4:
        return 4
    return min(percentual, 100)


def _serie(itens):
    visiveis = [
        item for item in itens if _positivo(item["valor"])
    ]
    maximo = max((item["valor"] for item in visiveis), default=0)
    linhas = []
    for item in visiveis:
        linhas.append(
            {
                "rotulo": item["rotulo"],
                "valor": item["valor"],
                "href": item.get("href") or "",
                "alerta": bool(item.get("alerta")),
                "monetario": bool(item.get("monetario")),
                "percentual": _percentual(item["valor"], maximo),
            }
        )
    return linhas


def montar_paineis(indicadores):
    indicadores = indicadores or {}
    url_ordens = reverse("servicos:lista_ordens")
    url_calibracoes = reverse("servicos:lista_calibracoes")
    url_instrumentos = reverse("servicos:lista_instrumentos")
    url_orcamentos = reverse("servicos:lista_orcamentos")
    url_cobrancas = reverse("servicos:lista_cobrancas")

    operacao_series = _serie(
        [
            {
                "rotulo": "Abertas",
                "valor": indicadores.get("os_abertas") or 0,
                "href": f"{url_ordens}?status=aberta",
            },
            {
                "rotulo": "Recebidas",
                "valor": indicadores.get("os_recebidas") or 0,
                "href": f"{url_ordens}?status=recebida",
            },
            {
                "rotulo": "Em execução",
                "valor": indicadores.get("os_em_execucao") or 0,
                "href": f"{url_ordens}?status=em_execucao",
            },
            {
                "rotulo": "Aguardando revisão",
                "valor": indicadores.get("os_aguardando_revisao") or 0,
                "href": f"{url_ordens}?status=aguardando_revisao",
            },
            {
                "rotulo": "Prontas para entrega",
                "valor": indicadores.get("os_prontas_entrega") or 0,
                "href": f"{url_ordens}?status=concluida",
            },
            {
                "rotulo": "Entregues",
                "valor": indicadores.get("os_entregues") or 0,
                "href": f"{url_ordens}?status=entregue",
            },
            {
                "rotulo": "Atrasadas",
                "valor": indicadores.get("os_atrasadas") or 0,
                "href": f"{url_ordens}?atrasadas=1",
                "alerta": True,
            },
        ]
    )
    operacao_kpis = _serie(
        [
            {
                "rotulo": "OS em execução",
                "valor": indicadores.get("os_em_execucao") or 0,
                "href": f"{url_ordens}?status=em_execucao",
            },
            {
                "rotulo": "Aguardando revisão",
                "valor": indicadores.get("os_aguardando_revisao") or 0,
                "href": f"{url_ordens}?status=aguardando_revisao",
            },
        ]
    )
    operacao_alertas = _serie(
        [
            {
                "rotulo": "OS atrasadas",
                "valor": indicadores.get("os_atrasadas") or 0,
                "href": f"{url_ordens}?atrasadas=1",
                "alerta": True,
            }
        ]
    )

    calibracoes_series = _serie(
        [
            {
                "rotulo": "Concluídas",
                "valor": indicadores.get("calibracoes_concluidas") or 0,
                "href": f"{url_calibracoes}?status=concluida",
            },
            {
                "rotulo": "Aprovadas",
                "valor": indicadores.get("calibracoes_aprovadas") or 0,
                "href": f"{url_calibracoes}?resultado=aprovado",
            },
            {
                "rotulo": "Reprovadas",
                "valor": indicadores.get("calibracoes_reprovadas") or 0,
                "href": f"{url_calibracoes}?resultado=reprovado",
            },
            {
                "rotulo": "Instrumentos vencidos",
                "valor": indicadores.get("instrumentos_vencidos") or 0,
                "href": url_instrumentos,
                "alerta": True,
            },
        ]
    )
    calibracoes_alertas = _serie(
        [
            {
                "rotulo": "Instrumentos com calibração vencida",
                "valor": indicadores.get("instrumentos_vencidos") or 0,
                "href": url_instrumentos,
                "alerta": True,
            }
        ]
    )

    comercial_series = _serie(
        [
            {
                "rotulo": "Em aberto",
                "valor": indicadores.get("orcamentos_rascunho") or 0,
                "href": f"{url_orcamentos}?status=rascunho",
            },
            {
                "rotulo": "Enviados",
                "valor": indicadores.get("orcamentos_enviados") or 0,
                "href": f"{url_orcamentos}?status=enviado",
            },
            {
                "rotulo": "Aprovados",
                "valor": indicadores.get("orcamentos_aprovados") or 0,
                "href": f"{url_orcamentos}?status=aprovado",
            },
            {
                "rotulo": "Vencidos",
                "valor": indicadores.get("orcamentos_vencidos") or 0,
                "href": f"{url_orcamentos}?status=enviado",
                "alerta": True,
            },
        ]
    )
    negociacao = indicadores.get("valor_negociacao") or Decimal("0.00")
    comercial_valores = _serie(
        [
            {
                "rotulo": "Valor em negociação",
                "valor": negociacao,
                "href": f"{url_orcamentos}?status=enviado",
                "monetario": True,
            }
        ]
    )
    comercial_alertas = _serie(
        [
            {
                "rotulo": "Orçamentos vencidos",
                "valor": indicadores.get("orcamentos_vencidos") or 0,
                "href": f"{url_orcamentos}?status=enviado",
                "alerta": True,
            }
        ]
    )

    financeiro_series = _serie(
        [
            {
                "rotulo": "A vencer",
                "valor": indicadores.get("cobrancas_a_vencer") or Decimal("0.00"),
                "href": url_cobrancas,
                "monetario": True,
            },
            {
                "rotulo": "Vencidas",
                "valor": indicadores.get("cobrancas_vencidas") or Decimal("0.00"),
                "href": f"{url_cobrancas}?vencidas=1",
                "alerta": True,
                "monetario": True,
            },
        ]
    )
    financeiro_kpis = _serie(
        [
            {
                "rotulo": "Contas a receber",
                "valor": indicadores.get("contas_a_receber") or Decimal("0.00"),
                "href": url_cobrancas,
                "monetario": True,
            },
            {
                "rotulo": "Recebido no mês",
                "valor": indicadores.get("recebido_mes") or Decimal("0.00"),
                "href": url_cobrancas,
                "monetario": True,
            },
        ]
    )
    financeiro_alertas = _serie(
        [
            {
                "rotulo": "Cobranças vencidas",
                "valor": indicadores.get("qtd_cobrancas_vencidas") or 0,
                "href": f"{url_cobrancas}?vencidas=1",
                "alerta": True,
            }
        ]
    )

    operacao = {
        "tem_dados": bool(operacao_series),
        "series": operacao_series,
        "kpis": operacao_kpis,
        "alertas": operacao_alertas,
    }
    calibracoes = {
        "tem_dados": bool(calibracoes_series),
        "series": calibracoes_series,
        "alertas": calibracoes_alertas,
    }
    comercial = {
        "tem_dados": bool(comercial_series or comercial_valores),
        "series": comercial_series,
        "valores": comercial_valores,
        "alertas": comercial_alertas,
    }
    financeiro = {
        "tem_dados": bool(financeiro_series or financeiro_kpis),
        "series": financeiro_series,
        "kpis": financeiro_kpis,
        "alertas": financeiro_alertas,
    }

    return {
        "operacao": operacao,
        "calibracoes": calibracoes,
        "comercial": comercial,
        "financeiro": financeiro,
        "tem_movimento": any(
            painel["tem_dados"]
            for painel in (operacao, calibracoes, comercial, financeiro)
        ),
    }

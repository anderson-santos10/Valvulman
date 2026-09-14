GRUPO_ADMINISTRADOR = "ADMINISTRADOR"
GRUPO_TECNICO = "TECNICO"
GRUPO_COMERCIAL = "COMERCIAL"
GRUPO_FINANCEIRO = "FINANCEIRO"
GRUPO_CONSULTA = "CONSULTA"

GRUPOS = (
    GRUPO_ADMINISTRADOR,
    GRUPO_TECNICO,
    GRUPO_COMERCIAL,
    GRUPO_FINANCEIRO,
    GRUPO_CONSULTA,
)

LEITURA_TECNICA = (
    "clientes.view_cliente",
    "servicos.view_valvula",
    "servicos.view_instrumento",
    "servicos.view_padraomedicao",
    "servicos.view_calibracao",
    "servicos.view_execucaovalvula",
    "servicos.view_certificadocalibracao",
    "servicos.view_ordemservico",
    "servicos.view_relatoriotecnico",
)

CONSULTA = LEITURA_TECNICA + (
    "servicos.view_orcamento",
    "servicos.view_cobranca",
    "servicos.view_pagamento",
)

TECNICO = LEITURA_TECNICA + (
    "servicos.add_valvula",
    "servicos.change_valvula",
    "servicos.add_instrumento",
    "servicos.change_instrumento",
    "servicos.add_padraomedicao",
    "servicos.change_padraomedicao",
    "servicos.add_calibracao",
    "servicos.change_calibracao",
    "servicos.add_execucaovalvula",
    "servicos.change_execucaovalvula",
    "servicos.concluir_calibracao",
    "servicos.revisar_calibracao",
    "servicos.reabrir_calibracao",
    "servicos.emitir_certificado",
    "servicos.add_ordemservico",
    "servicos.change_ordemservico",
    "servicos.receber_ordem",
    "servicos.iniciar_ordem",
    "servicos.revisar_ordem",
    "servicos.concluir_ordem",
    "servicos.entregar_ordem",
    "servicos.add_relatoriotecnico",
    "servicos.change_relatoriotecnico",
)

COMERCIAL = (
    "clientes.view_cliente",
    "clientes.add_cliente",
    "clientes.change_cliente",
    "servicos.view_orcamento",
    "servicos.add_orcamento",
    "servicos.change_orcamento",
    "servicos.enviar_orcamento",
    "servicos.aprovar_orcamento",
    "servicos.recusar_orcamento",
    "servicos.cancelar_orcamento",
    "servicos.gerar_ordem_servico",
    "servicos.view_ordemservico",
    "servicos.add_ordemservico",
    "servicos.view_instrumento",
    "servicos.view_relatoriotecnico",
)

FINANCEIRO = (
    "clientes.view_cliente",
    "servicos.view_orcamento",
    "servicos.view_ordemservico",
    "servicos.view_cobranca",
    "servicos.add_cobranca",
    "servicos.change_cobranca",
    "servicos.view_pagamento",
    "servicos.cancelar_cobranca",
    "servicos.registrar_pagamento",
)

PERMISSOES_GRUPOS = {
    GRUPO_TECNICO: TECNICO,
    GRUPO_COMERCIAL: COMERCIAL,
    GRUPO_FINANCEIRO: FINANCEIRO,
    GRUPO_CONSULTA: CONSULTA,
}

APPS_ADMINISTRADOR = ("clientes", "servicos", "acesso", "auth")

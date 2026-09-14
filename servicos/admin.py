from django.contrib import admin

from .forms import CalibracaoAdminForm, InstrumentoForm, PadraoMedicaoForm, ValvulaForm
from .models import (
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


class ValvulaRelatorioInline(admin.TabularInline):
    model = ValvulaRelatorio
    extra = 0


@admin.register(RelatorioTecnico)
class RelatorioTecnicoAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "numero_relatorio",
        "cliente",
        "setor",
        "data",
        "prazo_entrega",
        "data_aprovacao",
        "criado_em",
    )
    search_fields = ("numero_relatorio", "cliente__nome", "setor", "item")
    list_filter = ("data", "data_aprovacao", "criado_em")
    inlines = [ValvulaRelatorioInline]


@admin.register(ValvulaRelatorio)
class ValvulaRelatorioAdmin(admin.ModelAdmin):
    list_display = (
        "item",
        "relatorio",
        "numero_serie",
        "tag",
        "modelo",
        "fabricante",
        "pressao_psi",
    )
    search_fields = (
        "numero_serie",
        "tag",
        "modelo",
        "fabricante",
        "relatorio__numero_relatorio",
    )
    list_filter = ("fabricante",)


@admin.register(Valvula)
class ValvulaAdmin(admin.ModelAdmin):
    form = ValvulaForm
    list_display = (
        "codigo",
        "cliente",
        "tag",
        "numero_serie",
        "fabricante",
        "modelo",
        "ativo",
        "criado_em",
    )
    list_filter = ("cliente", "ativo", "unidade_pressao", "fabricante")
    search_fields = (
        "codigo",
        "tag",
        "numero_serie",
        "fabricante",
        "modelo",
        "cliente__nome",
    )
    ordering = ("cliente__nome", "codigo")


@admin.register(Instrumento)
class InstrumentoAdmin(admin.ModelAdmin):
    form = InstrumentoForm
    list_display = (
        "codigo",
        "cliente",
        "tipo",
        "tag",
        "numero_serie",
        "fabricante",
        "modelo",
        "ativo",
        "criado_em",
    )
    list_filter = ("cliente", "tipo", "ativo", "unidade", "fabricante")
    search_fields = (
        "codigo",
        "tag",
        "numero_serie",
        "fabricante",
        "modelo",
        "cliente__nome",
    )
    ordering = ("cliente__nome", "codigo")


@admin.register(PadraoMedicao)
class PadraoMedicaoAdmin(admin.ModelAdmin):
    form = PadraoMedicaoForm
    list_display = (
        "codigo",
        "identificacao",
        "tipo",
        "fabricante",
        "modelo",
        "numero_serie",
        "numero_certificado",
        "data_validade",
        "ativo",
        "criado_em",
    )
    list_filter = ("ativo", "unidade", "fabricante", "data_validade")
    search_fields = (
        "codigo",
        "identificacao",
        "tipo",
        "fabricante",
        "modelo",
        "numero_serie",
        "numero_certificado",
    )
    readonly_fields = ("criado_em", "atualizado_em")
    ordering = ("codigo",)


class PontoCalibracaoInline(admin.TabularInline):
    model = PontoCalibracao
    extra = 0
    exclude = ("erro",)
    ordering = ("ordem",)


@admin.register(Calibracao)
class CalibracaoAdmin(admin.ModelAdmin):
    form = CalibracaoAdminForm
    list_display = (
        "numero",
        "instrumento",
        "data_calibracao",
        "status",
        "resultado",
        "executor_nome",
        "revisor_nome",
        "data_validade",
        "padrao",
        "item_ordem_servico",
        "tolerancia",
        "criterio_aceitacao",
        "criado_em",
    )
    list_filter = ("status", "resultado", "data_calibracao", "instrumento__tipo")
    search_fields = (
        "numero",
        "instrumento__codigo",
        "instrumento__tag",
        "instrumento__numero_serie",
        "instrumento__cliente__nome",
        "procedimento",
        "padrao__codigo",
        "padrao_utilizado",
        "criterio_aceitacao",
    )
    readonly_fields = (
        "resultado",
        "executor_nome",
        "revisor_nome",
        "executado_em",
        "revisado_em",
        "data_validade",
        "padrao_utilizado",
    )
    ordering = ("-data_calibracao", "-criado_em")
    inlines = [PontoCalibracaoInline]

    def save_model(self, request, obj, form, change):
        obj.atualizar_validade()
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        calibracao = form.instance
        calibracao.aplicar_resultado_oficial()
        calibracao.save(update_fields=["resultado", "atualizado_em"])


@admin.register(PontoCalibracao)
class PontoCalibracaoAdmin(admin.ModelAdmin):
    exclude = ("erro",)
    list_display = (
        "calibracao",
        "ordem",
        "valor_referencia",
        "indicacao_instrumento",
        "erro",
    )
    search_fields = (
        "calibracao__numero",
        "calibracao__instrumento__codigo",
    )
    list_filter = ("calibracao__status",)
    ordering = ("calibracao", "ordem")


@admin.register(CertificadoCalibracao)
class CertificadoCalibracaoAdmin(admin.ModelAdmin):
    list_display = (
        "numero",
        "calibracao",
        "emitido_em",
        "status",
        "criado_em",
    )
    list_filter = ("status", "emitido_em")
    search_fields = (
        "numero",
        "calibracao__numero",
        "calibracao__instrumento__codigo",
        "calibracao__instrumento__tag",
        "calibracao__instrumento__numero_serie",
        "calibracao__instrumento__cliente__nome",
    )
    readonly_fields = (
        "calibracao",
        "numero",
        "emitido_em",
        "status",
        "criado_em",
        "atualizado_em",
        "token_validacao",
    )
    ordering = ("-emitido_em",)

    def has_add_permission(self, request):
        return False


class ItemOrdemServicoInline(admin.TabularInline):
    model = ItemOrdemServico
    extra = 0


@admin.register(OrdemServico)
class OrdemServicoAdmin(admin.ModelAdmin):
    list_display = (
        "numero",
        "cliente",
        "data_entrada",
        "data_previsao_entrega",
        "data_entrega",
        "status",
        "criado_em",
    )
    list_filter = ("status", "data_entrada")
    search_fields = ("numero", "cliente__nome", "solicitante")
    readonly_fields = ("numero", "criado_em", "atualizado_em", "data_entrega")
    ordering = ("-criado_em",)
    inlines = [ItemOrdemServicoInline]


@admin.register(ItemOrdemServico)
class ItemOrdemServicoAdmin(admin.ModelAdmin):
    list_display = (
        "ordem_servico",
        "tipo_equipamento",
        "instrumento",
        "valvula",
        "servico_solicitado",
        "status",
        "criado_em",
    )
    list_filter = ("status", "servico_solicitado", "tipo_equipamento")
    search_fields = (
        "ordem_servico__numero",
        "instrumento__codigo",
        "instrumento__tag",
        "valvula__codigo",
        "valvula__tag",
    )
    ordering = ("-criado_em",)


@admin.register(ExecucaoValvula)
class ExecucaoValvulaAdmin(admin.ModelAdmin):
    list_display = (
        "ordem_numero",
        "cliente_nome",
        "valvula_codigo",
        "servico",
        "status",
        "resultado",
        "executor_nome",
        "data_inicio",
    )
    list_filter = ("status", "resultado", "data_inicio")
    search_fields = (
        "item_ordem_servico__ordem_servico__numero",
        "item_ordem_servico__ordem_servico__cliente__nome",
        "valvula_codigo",
        "valvula_tag",
        "valvula_numero_serie",
        "executor_nome",
    )
    readonly_fields = (
        "valvula_codigo",
        "valvula_tag",
        "valvula_numero_serie",
        "valvula_fabricante",
        "valvula_modelo",
        "valvula_diametro_nominal",
        "valvula_pressao_ajuste",
        "valvula_unidade_pressao",
        "executor_nome",
        "revisor_nome",
        "executado_em",
        "revisado_em",
        "criado_em",
        "atualizado_em",
    )
    ordering = ("-criado_em",)

    @admin.display(description="OS")
    def ordem_numero(self, obj):
        return obj.item_ordem_servico.ordem_servico.numero

    @admin.display(description="Cliente")
    def cliente_nome(self, obj):
        return obj.item_ordem_servico.ordem_servico.cliente.nome

    @admin.display(description="Serviço")
    def servico(self, obj):
        return obj.item_ordem_servico.get_servico_solicitado_display()


class ItemOrcamentoInline(admin.TabularInline):
    model = ItemOrcamento
    extra = 0
    readonly_fields = ("total",)


@admin.register(Orcamento)
class OrcamentoAdmin(admin.ModelAdmin):
    list_display = (
        "numero",
        "cliente",
        "data_emissao",
        "data_validade",
        "status",
        "criado_em",
    )
    list_filter = ("status", "data_emissao")
    search_fields = (
        "numero",
        "cliente__nome",
        "cliente__cnpj",
        "cliente_nome_snapshot",
        "cliente_documento_snapshot",
    )
    readonly_fields = (
        "numero",
        "cliente_nome_snapshot",
        "cliente_documento_snapshot",
        "cliente_endereco_snapshot",
        "criado_em",
        "atualizado_em",
    )
    ordering = ("-data_emissao", "-criado_em")
    inlines = [ItemOrcamentoInline]


@admin.register(ItemOrcamento)
class ItemOrcamentoAdmin(admin.ModelAdmin):
    list_display = (
        "orcamento",
        "servico",
        "tipo_equipamento",
        "instrumento",
        "valvula",
        "quantidade",
        "valor_unitario",
        "desconto",
        "total",
    )
    search_fields = (
        "orcamento__numero",
        "descricao",
        "instrumento__codigo",
        "instrumento_codigo_snapshot",
        "valvula__codigo",
        "valvula_codigo_snapshot",
    )
    list_filter = ("servico",)
    readonly_fields = ("total",)
    ordering = ("orcamento", "ordem")


@admin.register(Cobranca)
class CobrancaAdmin(admin.ModelAdmin):
    list_display = (
        "numero",
        "cliente",
        "valor_final",
        "data_vencimento",
        "status",
        "criado_em",
    )
    list_filter = ("status", "forma_pagamento", "data_vencimento")
    search_fields = (
        "numero",
        "cliente__nome",
        "cliente__cnpj",
        "ordem_servico__numero",
        "orcamento__numero",
    )
    readonly_fields = ("numero", "valor_final", "criado_em", "atualizado_em")
    ordering = ("-data_emissao", "-criado_em")


@admin.register(Pagamento)
class PagamentoAdmin(admin.ModelAdmin):
    list_display = (
        "cobranca",
        "data_pagamento",
        "valor",
        "forma_pagamento",
        "criado_em",
    )
    search_fields = ("cobranca__numero", "cobranca__cliente__nome")
    list_filter = ("forma_pagamento", "data_pagamento")
    readonly_fields = ("criado_em",)
    ordering = ("-data_pagamento", "-pk")


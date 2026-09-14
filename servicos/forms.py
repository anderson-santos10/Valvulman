from decimal import Decimal

from django import forms
from django.db.models import Q
from django.forms.models import BaseInlineFormSet, inlineformset_factory

from clientes.models import Cliente

from .models import (
    Calibracao,
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
    ResultadoExecucaoValvula,
    SUGESTOES_CONDICAO_RECEBIMENTO,
    TipoEquipamento,
    UnidadePressao,
    Valvula,
)


INPUT_CLASS = (
    "w-full px-4 py-2 border rounded-lg focus:ring-2 "
    "focus:ring-indigo-500 focus:outline-none border-gray-300"
)


class RelatorioTecnicoForm(forms.ModelForm):

    class Meta:

        model = RelatorioTecnico

        fields = [
            "cliente",

            "numero_relatorio",

            "folha",

            "item",

            "setor",

            "data",

            # Motivo do relatório
            "motivo_solicitacao_cliente",
            "motivo_manutencao_corretiva",
            "motivo_garantia",
            "motivo_manutencao_preventiva",
            "motivo_venda",

            # Observações
            "observacoes",

            # Motivo principal da reforma
            "motivo_instalacao_irregular",
            "motivo_escolha_inadequada",
            "motivo_condicoes_criticas",
            "motivo_entrada_impurezas",
            "motivo_manuseio_irregular",
            "motivo_transporte_irregular",
            "motivo_desgaste_normal",
            "motivo_lacre_quebrado",

            # Prazo
            "prazo_entrega",

            # Aprovação
            "data_aprovacao",
        ]

        widgets = {

            "data": forms.DateInput(
                format="%Y-%m-%d",
                attrs={
                    "type": "date"
                }
            ),

            "prazo_entrega": forms.DateInput(
                format="%Y-%m-%d",
                attrs={
                    "type": "date"
                }
            ),

            "data_aprovacao": forms.DateInput(
                format="%Y-%m-%d",
                attrs={
                    "type": "date"
                }
            ),

            "observacoes": forms.Textarea(
                attrs={
                    "rows": 6
                }
            ),
        }


class ValvulaForm(forms.ModelForm):
    class Meta:
        model = Valvula
        fields = [
            "cliente",
            "codigo",
            "tag",
            "numero_serie",
            "fabricante",
            "modelo",
            "diametro_nominal",
            "pressao_ajuste",
            "unidade_pressao",
            "observacoes",
            "ativo",
        ]
        widgets = {
            "cliente": forms.Select(attrs={"class": INPUT_CLASS}),
            "codigo": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": "Ex.: PSV-001"}
            ),
            "tag": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": "TAG do cliente"}
            ),
            "numero_serie": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": "Número de série do fabricante"}
            ),
            "fabricante": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "modelo": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "diametro_nominal": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": 'Ex.: 1" ou DN 25'}
            ),
            "pressao_ajuste": forms.NumberInput(
                attrs={"class": INPUT_CLASS, "step": "any", "min": "0"}
            ),
            "unidade_pressao": forms.Select(attrs={"class": INPUT_CLASS}),
            "observacoes": forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 4}),
            "ativo": forms.CheckboxInput(),
        }

    def clean_codigo(self):
        codigo = (self.cleaned_data.get("codigo") or "").strip()
        if not codigo:
            raise forms.ValidationError("Informe o código interno da válvula.")
        return codigo

    def clean(self):
        cleaned = super().clean()
        pressao = cleaned.get("pressao_ajuste")
        unidade = cleaned.get("unidade_pressao")
        if pressao is not None and not unidade:
            self.add_error(
                "unidade_pressao",
                "Informe a unidade da pressão de ajuste.",
            )
        if pressao is None and not unidade:
            cleaned["unidade_pressao"] = UnidadePressao.PSI
        return cleaned


class InstrumentoForm(forms.ModelForm):
    class Meta:
        model = Instrumento
        fields = [
            "cliente",
            "codigo",
            "tag",
            "numero_serie",
            "tipo",
            "fabricante",
            "modelo",
            "faixa_minima",
            "faixa_maxima",
            "unidade",
            "resolucao",
            "observacoes",
            "ativo",
        ]
        widgets = {
            "cliente": forms.Select(attrs={"class": INPUT_CLASS}),
            "codigo": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": "Ex.: MAN-001"}
            ),
            "tag": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": "TAG do cliente"}
            ),
            "numero_serie": forms.TextInput(
                attrs={
                    "class": INPUT_CLASS,
                    "placeholder": "Número de série do fabricante",
                }
            ),
            "tipo": forms.Select(attrs={"class": INPUT_CLASS}),
            "fabricante": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "modelo": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "faixa_minima": forms.NumberInput(
                attrs={"class": INPUT_CLASS, "step": "any"}
            ),
            "faixa_maxima": forms.NumberInput(
                attrs={"class": INPUT_CLASS, "step": "any"}
            ),
            "unidade": forms.Select(attrs={"class": INPUT_CLASS}),
            "resolucao": forms.NumberInput(
                attrs={"class": INPUT_CLASS, "step": "any", "min": "0"}
            ),
            "observacoes": forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 4}),
            "ativo": forms.CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["cliente"].disabled = True

    def clean_codigo(self):
        codigo = (self.cleaned_data.get("codigo") or "").strip()
        if not codigo:
            raise forms.ValidationError("Informe o código interno do instrumento.")
        return codigo

    def clean(self):
        cleaned = super().clean()
        cliente = cleaned.get("cliente") or getattr(self.instance, "cliente", None)
        codigo = cleaned.get("codigo")
        faixa_minima = cleaned.get("faixa_minima")
        faixa_maxima = cleaned.get("faixa_maxima")
        unidade = cleaned.get("unidade")
        resolucao = cleaned.get("resolucao")

        if cliente and codigo:
            duplicados = Instrumento.objects.filter(
                cliente=cliente,
                codigo=codigo,
            )
            if self.instance.pk:
                duplicados = duplicados.exclude(pk=self.instance.pk)
            if duplicados.exists():
                self.add_error(
                    "codigo",
                    "Já existe um instrumento com este código para este cliente.",
                )

        if faixa_minima is not None and faixa_maxima is not None:
            if faixa_minima > faixa_maxima:
                self.add_error(
                    "faixa_minima",
                    "O limite inferior da faixa não pode ser maior que o limite superior.",
                )

        precisa_unidade = any(
            valor is not None for valor in (faixa_minima, faixa_maxima, resolucao)
        )
        if precisa_unidade and not unidade:
            self.add_error(
                "unidade",
                "Informe a unidade da faixa de medição e da resolução.",
            )
        if not precisa_unidade and not unidade:
            cleaned["unidade"] = UnidadePressao.PSI
        return cleaned


class PadraoMedicaoForm(forms.ModelForm):
    class Meta:
        model = PadraoMedicao
        fields = [
            "codigo",
            "identificacao",
            "tipo",
            "fabricante",
            "modelo",
            "numero_serie",
            "faixa_minima",
            "faixa_maxima",
            "unidade",
            "resolucao",
            "numero_certificado",
            "data_calibracao",
            "data_validade",
            "observacoes",
            "ativo",
        ]
        widgets = {
            "codigo": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": "Ex.: PAD-0001"}
            ),
            "identificacao": forms.TextInput(
                attrs={
                    "class": INPUT_CLASS,
                    "placeholder": "Ex.: Calibrador de pressão digital",
                }
            ),
            "tipo": forms.TextInput(
                attrs={
                    "class": INPUT_CLASS,
                    "placeholder": "Ex.: Calibrador de pressão",
                }
            ),
            "fabricante": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "modelo": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "numero_serie": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "faixa_minima": forms.NumberInput(
                attrs={"class": INPUT_CLASS, "step": "any"}
            ),
            "faixa_maxima": forms.NumberInput(
                attrs={"class": INPUT_CLASS, "step": "any"}
            ),
            "unidade": forms.Select(attrs={"class": INPUT_CLASS}),
            "resolucao": forms.NumberInput(
                attrs={"class": INPUT_CLASS, "step": "any", "min": "0"}
            ),
            "numero_certificado": forms.TextInput(
                attrs={
                    "class": INPUT_CLASS,
                    "placeholder": "Ex.: CERT-PAD-2026-001",
                }
            ),
            "data_calibracao": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"class": INPUT_CLASS, "type": "date"},
            ),
            "data_validade": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"class": INPUT_CLASS, "type": "date"},
            ),
            "observacoes": forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 4}),
            "ativo": forms.CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["codigo"].required = False
        if self.instance.pk:
            self.fields["codigo"].disabled = True
        else:
            self.fields.pop("ativo")
        self.fields["data_calibracao"].input_formats = ["%Y-%m-%d"]
        self.fields["data_validade"].input_formats = ["%Y-%m-%d"]

    def clean_codigo(self):
        if self.instance.pk:
            return self.instance.codigo
        return (self.cleaned_data.get("codigo") or "").strip()

    def clean_identificacao(self):
        identificacao = (self.cleaned_data.get("identificacao") or "").strip()
        if not identificacao:
            raise forms.ValidationError("Informe a identificação do padrão.")
        return identificacao

    def clean_resolucao(self):
        resolucao = self.cleaned_data.get("resolucao")
        if resolucao is not None and resolucao < 0:
            raise forms.ValidationError("A resolução não pode ser negativa.")
        return resolucao

    def clean(self):
        cleaned = super().clean()
        codigo = cleaned.get("codigo")
        faixa_minima = cleaned.get("faixa_minima")
        faixa_maxima = cleaned.get("faixa_maxima")
        unidade = cleaned.get("unidade")
        resolucao = cleaned.get("resolucao")
        data_calibracao = cleaned.get("data_calibracao")
        data_validade = cleaned.get("data_validade")

        if codigo:
            duplicados = PadraoMedicao.objects.filter(codigo=codigo)
            if self.instance.pk:
                duplicados = duplicados.exclude(pk=self.instance.pk)
            if duplicados.exists():
                self.add_error("codigo", "Já existe um padrão com este código.")

        if faixa_minima is not None and faixa_maxima is not None:
            if faixa_minima > faixa_maxima:
                self.add_error(
                    "faixa_minima",
                    "O limite inferior da faixa não pode ser maior que o limite superior.",
                )

        precisa_unidade = any(
            valor is not None for valor in (faixa_minima, faixa_maxima, resolucao)
        )
        if precisa_unidade and not unidade:
            self.add_error(
                "unidade",
                "Informe a unidade da faixa de medição e da resolução.",
            )
        if not precisa_unidade and not unidade:
            cleaned["unidade"] = UnidadePressao.PSI

        if data_calibracao and data_validade and data_calibracao > data_validade:
            self.add_error(
                "data_validade",
                "A validade do certificado do padrão não pode ser anterior à data de calibração do padrão.",
            )
        return cleaned


class CalibracaoForm(forms.ModelForm):
    class Meta:
        model = Calibracao
        fields = [
            "instrumento",
            "item_ordem_servico",
            "numero",
            "data_calibracao",
            "procedimento",
            "padrao",
            "criterio_aceitacao",
            "tolerancia",
            "intervalo_validade_meses",
            "observacoes",
        ]
        widgets = {
            "instrumento": forms.Select(attrs={"class": INPUT_CLASS}),
            "item_ordem_servico": forms.HiddenInput(),
            "numero": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": "Ex.: CAL-0001"}
            ),
            "data_calibracao": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"class": INPUT_CLASS, "type": "date"},
            ),
            "procedimento": forms.TextInput(
                attrs={
                    "class": INPUT_CLASS,
                    "placeholder": "Ex.: PROC-DEMO-MAN-001",
                    "list": "procedimentos-sugeridos",
                }
            ),
            "padrao": forms.Select(attrs={"class": INPUT_CLASS}),
            "criterio_aceitacao": forms.TextInput(
                attrs={
                    "class": INPUT_CLASS,
                    "placeholder": "Ex.: Erro máximo permitido conforme tolerância configurada",
                    "list": "criterios-sugeridos",
                }
            ),
            "tolerancia": forms.NumberInput(
                attrs={"class": INPUT_CLASS, "step": "any", "min": "0"}
            ),
            "observacoes": forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 4}),
            "intervalo_validade_meses": forms.NumberInput(
                attrs={
                    "class": INPUT_CLASS,
                    "min": "1",
                    "step": "1",
                    "placeholder": "Ex.: 12",
                }
            ),
        }

    def __init__(self, *args, item_os=None, **kwargs):
        self.item_os_inicial = item_os
        super().__init__(*args, **kwargs)
        self.fields["instrumento"].queryset = Instrumento.objects.select_related(
            "cliente"
        ).order_by("cliente__nome", "codigo")
        self.fields["instrumento"].label_from_instance = (
            lambda obj: f"{obj.codigo} — {obj.cliente.nome}"
        )
        self.fields["intervalo_validade_meses"].required = False
        self.fields["intervalo_validade_meses"].help_text = (
            "Prazo documental em meses (ex.: 6, 12 ou 24). Deixe em branco se não houver validade definida."
        )
        self.fields["numero"].required = False
        self.fields["padrao"].required = False
        self.fields["padrao"].empty_label = "Selecione o padrão de medição"
        queryset_padrao = PadraoMedicao.objects.filter(ativo=True)
        if self.instance.padrao_id:
            queryset_padrao = PadraoMedicao.objects.filter(
                Q(ativo=True) | Q(pk=self.instance.padrao_id)
            )
        self.fields["padrao"].queryset = queryset_padrao.order_by("codigo")
        self.fields["padrao"].label_from_instance = lambda obj: obj.rotulo_selecao()
        self.fields["item_ordem_servico"].required = False
        self.fields["item_ordem_servico"].queryset = ItemOrdemServico.objects.select_related(
            "instrumento",
            "ordem_servico",
        )
        item = self.instance.item_ordem_servico if self.instance.pk else None
        if not item:
            item = getattr(self, "item_os_inicial", None)
        if item:
            self.fields["instrumento"].disabled = True
            self.fields["instrumento"].queryset = Instrumento.objects.filter(
                pk=item.instrumento_id
            )
            self.initial.setdefault("instrumento", item.instrumento_id)
            self.initial.setdefault("item_ordem_servico", item.pk)
        if self.instance.pk:
            self.fields["instrumento"].disabled = True

    def clean_numero(self):
        return (self.cleaned_data.get("numero") or "").strip()

    def clean_criterio_aceitacao(self):
        return (self.cleaned_data.get("criterio_aceitacao") or "").strip()

    def clean_tolerancia(self):
        tolerancia = self.cleaned_data.get("tolerancia")
        if tolerancia is not None and tolerancia < 0:
            raise forms.ValidationError("A tolerância não pode ser negativa.")
        return tolerancia

    def clean_intervalo_validade_meses(self):
        intervalo = self.cleaned_data.get("intervalo_validade_meses")
        if intervalo is not None and intervalo < 1:
            raise forms.ValidationError(
                "O intervalo de validade, se informado, deve ser de pelo menos 1 mês."
            )
        return intervalo

    def clean(self):
        cleaned = super().clean()
        instrumento = cleaned.get("instrumento") or getattr(
            self.instance, "instrumento", None
        )
        numero = cleaned.get("numero")

        if instrumento and numero:
            duplicados = Calibracao.objects.filter(
                instrumento=instrumento,
                numero=numero,
            )
            if self.instance.pk:
                duplicados = duplicados.exclude(pk=self.instance.pk)
            if duplicados.exists():
                self.add_error(
                    "numero",
                    "Já existe uma calibração com este número para este instrumento.",
                )
        padrao = cleaned.get("padrao")
        data_calibracao = cleaned.get("data_calibracao") or getattr(
            self.instance, "data_calibracao", None
        )
        if padrao:
            permitir_inativo = self.instance.padrao_id == padrao.pk
            erro = padrao.validar_uso(
                data_calibracao,
                permitir_inativo=permitir_inativo,
            )
            if erro:
                self.add_error("padrao", erro)
        item = cleaned.get("item_ordem_servico")
        if item:
            if not item.exige_calibracao:
                self.add_error(
                    "item_ordem_servico",
                    "Só é possível registrar calibração em item de manômetro com serviço de calibração.",
                )
            cleaned["instrumento"] = item.instrumento
            if instrumento and item.instrumento_id != instrumento.pk:
                self.add_error(
                    "instrumento",
                    "A calibração deve usar o mesmo instrumento do item da ordem de serviço.",
                )
            if (
                instrumento
                and item.ordem_servico.cliente_id != instrumento.cliente_id
            ):
                self.add_error(
                    "item_ordem_servico",
                    "A ordem de serviço e o instrumento devem pertencer ao mesmo cliente.",
                )
        return cleaned


class CalibracaoAdminForm(CalibracaoForm):
    class Meta(CalibracaoForm.Meta):
        fields = CalibracaoForm.Meta.fields + ["status"]
        widgets = {
            **CalibracaoForm.Meta.widgets,
            "status": forms.Select(attrs={"class": INPUT_CLASS}),
        }


class ExecucaoValvulaForm(forms.ModelForm):
    class Meta:
        model = ExecucaoValvula
        fields = [
            "data_inicio",
            "data_fim",
            "descricao_servico",
            "observacoes",
            "resultado",
            "observacoes_revisao",
        ]
        widgets = {
            "data_inicio": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"class": INPUT_CLASS, "type": "date"},
            ),
            "data_fim": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"class": INPUT_CLASS, "type": "date"},
            ),
            "descricao_servico": forms.Textarea(
                attrs={"class": INPUT_CLASS, "rows": 4}
            ),
            "observacoes": forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 3}),
            "resultado": forms.Select(attrs={"class": INPUT_CLASS}),
            "observacoes_revisao": forms.Textarea(
                attrs={"class": INPUT_CLASS, "rows": 3}
            ),
        }

    def __init__(self, *args, somente_revisao=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.somente_revisao = somente_revisao
        self.fields["data_fim"].required = False
        self.fields["observacoes"].required = False
        self.fields["descricao_servico"].required = False
        self.fields["observacoes_revisao"].required = False
        if somente_revisao:
            for nome in (
                "data_inicio",
                "data_fim",
                "descricao_servico",
                "observacoes",
                "resultado",
            ):
                self.fields[nome].disabled = True

    def clean(self):
        cleaned = super().clean()
        inicio = cleaned.get("data_inicio") or getattr(self.instance, "data_inicio", None)
        fim = cleaned.get("data_fim")
        if inicio and fim and fim < inicio:
            self.add_error(
                "data_fim",
                "A data de fim não pode ser anterior à data de início.",
            )
        resultado = cleaned.get("resultado")
        if resultado == ResultadoExecucaoValvula.PENDENTE:
            cleaned["resultado"] = ResultadoExecucaoValvula.PENDENTE
        return cleaned


class PontoCalibracaoForm(forms.ModelForm):
    class Meta:
        model = PontoCalibracao
        fields = [
            "ordem",
            "valor_referencia",
            "indicacao_instrumento",
            "observacoes",
        ]
        widgets = {
            "ordem": forms.NumberInput(
                attrs={"class": INPUT_CLASS, "min": "1", "step": "1"}
            ),
            "valor_referencia": forms.NumberInput(
                attrs={"class": INPUT_CLASS, "step": "any"}
            ),
            "indicacao_instrumento": forms.NumberInput(
                attrs={"class": INPUT_CLASS, "step": "any"}
            ),
            "observacoes": forms.TextInput(attrs={"class": INPUT_CLASS}),
        }

    def __init__(self, *args, instrumento=None, **kwargs):
        self.instrumento = instrumento
        super().__init__(*args, **kwargs)

    def clean_ordem(self):
        ordem = self.cleaned_data.get("ordem")
        if ordem is None or ordem < 1:
            raise forms.ValidationError("A ordem do ponto deve ser um número positivo.")
        return ordem

    def clean(self):
        cleaned = super().clean()
        referencia = cleaned.get("valor_referencia")
        instrumento = self.instrumento
        if referencia is None or instrumento is None:
            return cleaned
        minimo = instrumento.faixa_minima
        maximo = instrumento.faixa_maxima
        unidade = instrumento.unidade or ""
        if minimo is not None and referencia < minimo:
            self.add_error(
                "valor_referencia",
                f"O valor de referência está abaixo da faixa do instrumento ({instrumento.faixa_formatada or unidade}).",
            )
        if maximo is not None and referencia > maximo:
            self.add_error(
                "valor_referencia",
                f"O valor de referência está acima da faixa do instrumento ({instrumento.faixa_formatada or unidade}).",
            )
        return cleaned


class PontoCalibracaoFormSetBase(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        ordens = []
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            ordem = form.cleaned_data.get("ordem")
            if ordem in ordens:
                form.add_error(
                    "ordem",
                    "A ordem dos pontos deve ser única nesta calibração.",
                )
            else:
                ordens.append(ordem)


PontoCalibracaoFormSet = inlineformset_factory(
    Calibracao,
    PontoCalibracao,
    form=PontoCalibracaoForm,
    formset=PontoCalibracaoFormSetBase,
    extra=1,
    can_delete=True,
    min_num=0,
    validate_min=False,
)


class OrdemServicoForm(forms.ModelForm):
    class Meta:
        model = OrdemServico
        fields = [
            "cliente",
            "data_entrada",
            "data_previsao_entrega",
            "solicitante",
            "telefone_solicitante",
            "email_solicitante",
            "contato_solicitante",
            "responsavel_recebimento",
            "observacoes",
        ]
        widgets = {
            "cliente": forms.Select(attrs={"class": INPUT_CLASS, "id": "id_os_cliente"}),
            "data_entrada": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"class": INPUT_CLASS, "type": "date"},
            ),
            "data_previsao_entrega": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"class": INPUT_CLASS, "type": "date"},
            ),
            "solicitante": forms.TextInput(
                attrs={
                    "class": INPUT_CLASS,
                    "placeholder": "Ex.: João da Empresa ABC",
                    "id": "id_solicitante",
                }
            ),
            "telefone_solicitante": forms.TextInput(
                attrs={
                    "class": INPUT_CLASS,
                    "placeholder": "(14) 99999-9999",
                    "id": "id_telefone_solicitante",
                    "autocomplete": "tel",
                }
            ),
            "email_solicitante": forms.EmailInput(
                attrs={
                    "class": INPUT_CLASS,
                    "placeholder": "contato@empresa.com",
                    "id": "id_email_solicitante",
                    "autocomplete": "email",
                }
            ),
            "contato_solicitante": forms.TextInput(
                attrs={
                    "class": INPUT_CLASS,
                    "placeholder": "Observação extra de contato",
                }
            ),
            "responsavel_recebimento": forms.TextInput(
                attrs={
                    "class": INPUT_CLASS,
                    "placeholder": "Quem recebeu os equipamentos",
                }
            ),
            "observacoes": forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cliente"].queryset = Cliente.objects.order_by("nome")
        if self.instance.pk:
            self.fields["cliente"].disabled = True
        self.fields["data_entrada"].input_formats = ["%Y-%m-%d"]
        self.fields["data_previsao_entrega"].input_formats = ["%Y-%m-%d"]
        self.fields["data_previsao_entrega"].required = False

    def clean(self):
        cleaned = super().clean()
        entrada = cleaned.get("data_entrada")
        previsao = cleaned.get("data_previsao_entrega")
        if entrada and previsao and previsao < entrada:
            self.add_error(
                "data_previsao_entrega",
                "A previsão de entrega não pode ser anterior à data de entrada.",
            )
        return cleaned


class ItemOrdemServicoForm(forms.ModelForm):
    class Meta:
        model = ItemOrdemServico
        fields = [
            "tipo_equipamento",
            "instrumento",
            "valvula",
            "servico_solicitado",
            "condicao_recebimento",
            "observacoes_recebimento",
            "observacoes",
        ]
        widgets = {
            "tipo_equipamento": forms.Select(attrs={"class": INPUT_CLASS}),
            "instrumento": forms.Select(attrs={"class": INPUT_CLASS}),
            "valvula": forms.Select(attrs={"class": INPUT_CLASS}),
            "servico_solicitado": forms.Select(attrs={"class": INPUT_CLASS}),
            "condicao_recebimento": forms.TextInput(
                attrs={
                    "class": INPUT_CLASS,
                    "placeholder": "Ex.: Bom estado",
                    "list": "sugestoes-condicao-recebimento",
                }
            ),
            "observacoes_recebimento": forms.TextInput(
                attrs={
                    "class": INPUT_CLASS,
                    "placeholder": "Observações do recebimento",
                }
            ),
            "observacoes": forms.TextInput(attrs={"class": INPUT_CLASS}),
        }

    def __init__(self, *args, cliente=None, **kwargs):
        self.cliente = cliente
        super().__init__(*args, **kwargs)
        instrumentos = Instrumento.objects.select_related("cliente").order_by("codigo")
        valvulas = Valvula.objects.select_related("cliente").order_by("codigo")
        if cliente is not None:
            instrumentos = instrumentos.filter(cliente=cliente, ativo=True)
            valvulas = valvulas.filter(cliente=cliente, ativo=True)
            if self.instance.instrumento_id:
                instrumentos = Instrumento.objects.filter(
                    Q(pk=self.instance.instrumento_id) | Q(cliente=cliente, ativo=True)
                ).select_related("cliente").order_by("codigo")
            if self.instance.valvula_id:
                valvulas = Valvula.objects.filter(
                    Q(pk=self.instance.valvula_id) | Q(cliente=cliente, ativo=True)
                ).select_related("cliente").order_by("codigo")
        self.fields["instrumento"].queryset = instrumentos
        self.fields["valvula"].queryset = valvulas
        self.fields["instrumento"].required = False
        self.fields["valvula"].required = False
        self.fields["instrumento"].label_from_instance = (
            lambda obj: f"{obj.codigo} — {obj.tag or obj.numero_serie or obj.cliente.nome}"
        )
        self.fields["valvula"].label_from_instance = (
            lambda obj: f"{obj.codigo} — {obj.tag or obj.numero_serie or obj.cliente.nome}"
        )
        if self.instance.pk and self.instance.calibracao_atual:
            self.fields["tipo_equipamento"].disabled = True
            self.fields["instrumento"].disabled = True
            self.fields["valvula"].disabled = True

    def clean_instrumento(self):
        instrumento = self.cleaned_data.get("instrumento")
        if self.fields["instrumento"].disabled:
            return self.instance.instrumento
        if instrumento and self.cliente and instrumento.cliente_id != self.cliente.pk:
            raise forms.ValidationError(
                "O instrumento deve pertencer ao mesmo cliente da ordem de serviço."
            )
        return instrumento

    def clean_valvula(self):
        valvula = self.cleaned_data.get("valvula")
        if self.fields["valvula"].disabled:
            return self.instance.valvula
        if valvula and self.cliente and valvula.cliente_id != self.cliente.pk:
            raise forms.ValidationError(
                "A válvula deve pertencer ao mesmo cliente da ordem de serviço."
            )
        return valvula

    def clean(self):
        cleaned = super().clean()
        tipo = cleaned.get("tipo_equipamento") or self.instance.tipo_equipamento
        instrumento = cleaned.get("instrumento")
        valvula = cleaned.get("valvula")
        if tipo == TipoEquipamento.INSTRUMENTO:
            cleaned["valvula"] = None
            if not instrumento:
                self.add_error("instrumento", "Selecione o manômetro deste item.")
        elif tipo == TipoEquipamento.VALVULA:
            cleaned["instrumento"] = None
            if not valvula:
                self.add_error("valvula", "Selecione a válvula deste item.")
        return cleaned


class ItemOrdemServicoFormSetBase(BaseInlineFormSet):
    def __init__(self, *args, cliente=None, **kwargs):
        self.cliente = cliente
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs["cliente"] = self.cliente
        return kwargs

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        equipamentos = []
        ativos = 0
        for form in self.forms:
            if not form.cleaned_data:
                continue
            if form.cleaned_data.get("DELETE"):
                if form.instance.pk and form.instance.calibracoes.exists():
                    form.add_error(
                        None,
                        "Não é possível remover um item que já possui calibração vinculada.",
                    )
                continue
            ativos += 1
            instrumento = form.cleaned_data.get("instrumento")
            valvula = form.cleaned_data.get("valvula")
            chave = ("i", instrumento.pk) if instrumento else None
            if valvula:
                chave = ("v", valvula.pk)
            if chave and chave in equipamentos:
                campo = "instrumento" if chave[0] == "i" else "valvula"
                form.add_error(
                    campo,
                    "Este equipamento já foi incluído nesta ordem de serviço.",
                )
            elif chave:
                equipamentos.append(chave)
        if ativos < 1:
            raise forms.ValidationError(
                "Inclua pelo menos um equipamento na ordem de serviço."
            )


ItemOrdemServicoFormSet = inlineformset_factory(
    OrdemServico,
    ItemOrdemServico,
    form=ItemOrdemServicoForm,
    formset=ItemOrdemServicoFormSetBase,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=False,
)


class OrcamentoForm(forms.ModelForm):
    class Meta:
        model = Orcamento
        fields = [
            "cliente",
            "data_emissao",
            "data_validade",
            "condicoes_comerciais",
            "observacoes",
        ]
        widgets = {
            "cliente": forms.Select(attrs={"class": INPUT_CLASS, "id": "id_os_cliente"}),
            "data_emissao": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"class": INPUT_CLASS, "type": "date"},
            ),
            "data_validade": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"class": INPUT_CLASS, "type": "date"},
            ),
            "condicoes_comerciais": forms.Textarea(
                attrs={"class": INPUT_CLASS, "rows": 3}
            ),
            "observacoes": forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cliente"].queryset = Cliente.objects.order_by("nome")
        if self.instance.pk:
            self.fields["cliente"].disabled = True
        self.fields["data_emissao"].input_formats = ["%Y-%m-%d"]
        self.fields["data_validade"].input_formats = ["%Y-%m-%d"]
        self.fields["data_validade"].required = False

    def clean(self):
        cleaned = super().clean()
        emissao = cleaned.get("data_emissao")
        validade = cleaned.get("data_validade")
        if emissao and validade and validade < emissao:
            self.add_error(
                "data_validade",
                "A validade da proposta não pode ser anterior à data de emissão.",
            )
        return cleaned


class ItemOrcamentoForm(forms.ModelForm):
    class Meta:
        model = ItemOrcamento
        fields = [
            "tipo_equipamento",
            "servico",
            "instrumento",
            "valvula",
            "descricao",
            "quantidade",
            "valor_unitario",
            "desconto",
            "ordem",
        ]
        widgets = {
            "tipo_equipamento": forms.Select(attrs={"class": INPUT_CLASS}),
            "servico": forms.Select(attrs={"class": INPUT_CLASS}),
            "instrumento": forms.Select(attrs={"class": INPUT_CLASS}),
            "valvula": forms.Select(attrs={"class": INPUT_CLASS}),
            "descricao": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "quantidade": forms.NumberInput(
                attrs={"class": INPUT_CLASS, "min": "1", "step": "1"}
            ),
            "valor_unitario": forms.NumberInput(
                attrs={"class": INPUT_CLASS, "min": "0", "step": "0.01"}
            ),
            "desconto": forms.NumberInput(
                attrs={"class": INPUT_CLASS, "min": "0", "step": "0.01"}
            ),
            "ordem": forms.HiddenInput(),
        }

    def __init__(self, *args, cliente=None, **kwargs):
        self.cliente = cliente
        super().__init__(*args, **kwargs)
        instrumentos = Instrumento.objects.select_related("cliente").order_by("codigo")
        valvulas = Valvula.objects.select_related("cliente").order_by("codigo")
        if cliente is not None:
            instrumentos = instrumentos.filter(cliente=cliente, ativo=True)
            valvulas = valvulas.filter(cliente=cliente, ativo=True)
            if self.instance.instrumento_id:
                instrumentos = Instrumento.objects.filter(
                    Q(pk=self.instance.instrumento_id) | Q(cliente=cliente, ativo=True)
                ).select_related("cliente").order_by("codigo")
            if self.instance.valvula_id:
                valvulas = Valvula.objects.filter(
                    Q(pk=self.instance.valvula_id) | Q(cliente=cliente, ativo=True)
                ).select_related("cliente").order_by("codigo")
        self.fields["instrumento"].queryset = instrumentos
        self.fields["valvula"].queryset = valvulas
        self.fields["instrumento"].required = False
        self.fields["valvula"].required = False
        self.fields["tipo_equipamento"].required = False
        self.fields["instrumento"].label_from_instance = (
            lambda obj: f"{obj.codigo} — {obj.tag or obj.numero_serie or obj.cliente.nome}"
        )
        self.fields["valvula"].label_from_instance = (
            lambda obj: f"{obj.codigo} — {obj.tag or obj.numero_serie or obj.cliente.nome}"
        )
        self.fields["desconto"].required = False
        self.fields["ordem"].required = False
        self.initial.setdefault("ordem", 1)

    def clean_instrumento(self):
        instrumento = self.cleaned_data.get("instrumento")
        if instrumento and self.cliente and instrumento.cliente_id != self.cliente.pk:
            raise forms.ValidationError(
                "O instrumento deve pertencer ao mesmo cliente do orçamento."
            )
        return instrumento

    def clean_valvula(self):
        valvula = self.cleaned_data.get("valvula")
        if valvula and self.cliente and valvula.cliente_id != self.cliente.pk:
            raise forms.ValidationError(
                "A válvula deve pertencer ao mesmo cliente do orçamento."
            )
        return valvula

    def clean(self):
        cleaned = super().clean()
        tipo = cleaned.get("tipo_equipamento") or ""
        instrumento = cleaned.get("instrumento")
        valvula = cleaned.get("valvula")
        if tipo == TipoEquipamento.INSTRUMENTO:
            cleaned["valvula"] = None
            valvula = None
        elif tipo == TipoEquipamento.VALVULA:
            cleaned["instrumento"] = None
            instrumento = None
        if instrumento and valvula:
            self.add_error(
                "valvula",
                "O item deve apontar para um manômetro ou para uma válvula, nunca para os dois.",
            )
        quantidade = cleaned.get("quantidade")
        valor = cleaned.get("valor_unitario")
        desconto = cleaned.get("desconto") or Decimal("0.00")
        cleaned["desconto"] = desconto
        if quantidade is not None and quantidade < 1:
            self.add_error("quantidade", "A quantidade deve ser maior que zero.")
        if valor is not None and valor < 0:
            self.add_error("valor_unitario", "O valor unitário não pode ser negativo.")
        if desconto < 0:
            self.add_error("desconto", "O desconto não pode ser negativo.")
        if quantidade and valor is not None:
            subtotal = quantidade * valor
            if desconto > subtotal:
                self.add_error(
                    "desconto",
                    "O desconto não pode ser maior que o subtotal do item.",
                )
        return cleaned


class ItemOrcamentoFormSetBase(BaseInlineFormSet):
    def __init__(self, *args, cliente=None, **kwargs):
        self.cliente = cliente
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs["cliente"] = self.cliente
        return kwargs

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        ativos = 0
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            ativos += 1
        if ativos < 1:
            raise forms.ValidationError("Inclua pelo menos um item no orçamento.")


ItemOrcamentoFormSet = inlineformset_factory(
    Orcamento,
    ItemOrcamento,
    form=ItemOrcamentoForm,
    formset=ItemOrcamentoFormSetBase,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=False,
)


class CobrancaForm(forms.ModelForm):
    class Meta:
        model = Cobranca
        fields = [
            "cliente",
            "orcamento",
            "ordem_servico",
            "descricao",
            "valor_original",
            "desconto",
            "acrescimo",
            "data_emissao",
            "data_vencimento",
            "forma_pagamento",
            "observacoes",
        ]
        widgets = {
            "cliente": forms.Select(attrs={"class": INPUT_CLASS, "id": "id_cobranca_cliente"}),
            "orcamento": forms.Select(attrs={"class": INPUT_CLASS, "id": "id_cobranca_orcamento"}),
            "ordem_servico": forms.Select(
                attrs={"class": INPUT_CLASS, "id": "id_cobranca_os"}
            ),
            "descricao": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "valor_original": forms.NumberInput(
                attrs={"class": INPUT_CLASS, "step": "0.01", "min": "0"}
            ),
            "desconto": forms.NumberInput(
                attrs={"class": INPUT_CLASS, "step": "0.01", "min": "0"}
            ),
            "acrescimo": forms.NumberInput(
                attrs={"class": INPUT_CLASS, "step": "0.01", "min": "0"}
            ),
            "data_emissao": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"class": INPUT_CLASS, "type": "date"},
            ),
            "data_vencimento": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"class": INPUT_CLASS, "type": "date"},
            ),
            "forma_pagamento": forms.Select(attrs={"class": INPUT_CLASS}),
            "observacoes": forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cliente"].queryset = Cliente.objects.order_by("nome")
        self.fields["orcamento"].required = False
        self.fields["ordem_servico"].required = False
        self.fields["forma_pagamento"].required = False
        self.fields["data_emissao"].input_formats = ["%Y-%m-%d"]
        self.fields["data_vencimento"].input_formats = ["%Y-%m-%d"]
        cliente = None
        if self.data.get("cliente"):
            cliente = Cliente.objects.filter(pk=self.data.get("cliente")).first()
        elif self.instance.pk:
            cliente = self.instance.cliente
        elif self.initial.get("cliente"):
            bruto = self.initial.get("cliente")
            if hasattr(bruto, "pk"):
                cliente = bruto
            elif str(bruto).isdigit():
                cliente = Cliente.objects.filter(pk=int(bruto)).first()
        orcamentos = Orcamento.objects.select_related("cliente").order_by("-data_emissao")
        ordens = OrdemServico.objects.select_related("cliente").order_by("-data_entrada")
        if cliente:
            orcamentos = orcamentos.filter(cliente=cliente)
            ordens = ordens.filter(cliente=cliente)
        self.fields["orcamento"].queryset = orcamentos
        self.fields["ordem_servico"].queryset = ordens
        if self.instance.pk:
            self.fields["cliente"].disabled = True

    def clean_valor_original(self):
        valor = self.cleaned_data.get("valor_original")
        if valor is None:
            raise forms.ValidationError("Informe o valor original.")
        if valor < 0:
            raise forms.ValidationError("O valor original não pode ser negativo.")
        return valor

    def clean(self):
        cleaned = super().clean()
        original = cleaned.get("valor_original") or Decimal("0.00")
        desconto = cleaned.get("desconto") or Decimal("0.00")
        acrescimo = cleaned.get("acrescimo") or Decimal("0.00")
        if original - desconto + acrescimo < 0:
            self.add_error("desconto", "O desconto não pode deixar o valor final negativo.")
        if original - desconto + acrescimo <= 0:
            self.add_error(
                "valor_original",
                "O valor final da cobrança deve ser maior que zero.",
            )
        return cleaned


class PagamentoForm(forms.ModelForm):
    class Meta:
        model = Pagamento
        fields = ["data_pagamento", "valor", "forma_pagamento", "observacoes"]
        widgets = {
            "data_pagamento": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"class": INPUT_CLASS, "type": "date"},
            ),
            "valor": forms.NumberInput(
                attrs={"class": INPUT_CLASS, "step": "0.01", "min": "0.01"}
            ),
            "forma_pagamento": forms.Select(attrs={"class": INPUT_CLASS}),
            "observacoes": forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 2}),
        }

    def __init__(self, *args, cobranca=None, **kwargs):
        self.cobranca = cobranca
        super().__init__(*args, **kwargs)
        self.fields["data_pagamento"].input_formats = ["%Y-%m-%d"]
        if cobranca is not None:
            self.instance.cobranca = cobranca

    def clean_valor(self):
        valor = self.cleaned_data.get("valor")
        if valor is None or valor <= 0:
            raise forms.ValidationError("O valor do pagamento deve ser maior que zero.")
        if self.cobranca and valor > self.cobranca.saldo_devedor():
            raise forms.ValidationError("O pagamento não pode ultrapassar o saldo da cobrança.")
        return valor

    def save(self, commit=True):
        pagamento = super().save(commit=False)
        if self.cobranca:
            pagamento.cobranca = self.cobranca
        if commit:
            pagamento.save()
        return pagamento


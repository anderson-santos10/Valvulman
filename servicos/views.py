import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import content_disposition_header
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from acesso.auditoria import registrar_auditoria
from acesso.mixins import PermissaoRequeridaMixin
from clientes.models import Cliente

from .forms import (
    CalibracaoForm,
    InstrumentoForm,
    PadraoMedicaoForm,
    PontoCalibracaoFormSet,
    RelatorioTecnicoForm,
    ValvulaForm,
)
from .models import (
    Calibracao,
    CertificadoCalibracao,
    Instrumento,
    ItemOrcamento,
    ItemOrdemServico,
    PadraoMedicao,
    RelatorioTecnico,
    ResultadoCalibracao,
    StatusCalibracao,
    StatusCertificado,
    StatusOrdemServico,
    TipoInstrumento,
    UnidadePressao,
    Valvula,
    ValvulaRelatorio,
)
from .operacao import historico_instrumento, historico_valvula
from .pdf import (
    PdfGenerationError,
    contexto_documento_certificado,
    gerar_pdf_certificado,
    nome_arquivo_pdf,
)

logger = logging.getLogger(__name__)

MOTIVOS_RELATORIO = (
    ("motivo_solicitacao_cliente", "Solicitação do Cliente"),
    ("motivo_manutencao_corretiva", "Manutenção corretiva"),
    ("motivo_garantia", "Garantia"),
    ("motivo_manutencao_preventiva", "Manutenção preventiva"),
    ("motivo_venda", "Incluso na venda"),
)

MOTIVOS_REFORMA = (
    ("motivo_instalacao_irregular", "Instalação irregular"),
    ("motivo_escolha_inadequada", "Escolha inadequada da válvula"),
    ("motivo_condicoes_criticas", "Condições críticas do fluido"),
    ("motivo_entrada_impurezas", "Entrada de impurezas"),
    ("motivo_manuseio_irregular", "Manuseio irregular"),
    ("motivo_transporte_irregular", "Transporte irregular"),
    ("motivo_desgaste_normal", "Desgaste normal"),
    ("motivo_lacre_quebrado", "Lacre quebrado"),
)


def _rotulos_marcados(relatorio, pares):
    return [rotulo for campo, rotulo in pares if getattr(relatorio, campo)]


def _extrair_valvulas_do_post(post_data, cliente=None):
    itens = post_data.getlist("valvula_item[]")
    numeros_serie = post_data.getlist("valvula_serie[]")
    tags = post_data.getlist("valvula_tag[]")
    diametros = post_data.getlist("valvula_diametro[]")
    modelos = post_data.getlist("valvula_modelo[]")
    fabricantes = post_data.getlist("valvula_fabricante[]")
    pressoes = post_data.getlist("valvula_pressao[]")
    servicos = post_data.getlist("valvula_servico[]")
    observacoes = post_data.getlist("valvula_observacao[]")
    cadastros = post_data.getlist("valvula_cadastro[]")

    total = max(
        len(itens),
        len(numeros_serie),
        len(tags),
        len(diametros),
        len(modelos),
        len(fabricantes),
        len(pressoes),
        len(servicos),
        len(observacoes),
        len(cadastros),
        0,
    )

    valvulas = []
    for i in range(total):
        item = itens[i] if i < len(itens) else str(i + 1)
        try:
            item = int(item)
        except (ValueError, TypeError):
            item = i + 1

        numero_serie = numeros_serie[i] if i < len(numeros_serie) else ""
        tag = tags[i] if i < len(tags) else ""
        diametro = diametros[i] if i < len(diametros) else ""
        modelo = modelos[i] if i < len(modelos) else ""
        fabricante = fabricantes[i] if i < len(fabricantes) else ""
        pressao = pressoes[i] if i < len(pressoes) else ""
        servico = servicos[i] if i < len(servicos) else ""
        observacao = observacoes[i] if i < len(observacoes) else ""
        cadastro_raw = cadastros[i] if i < len(cadastros) else ""

        valvula_id = None
        if str(cadastro_raw).strip():
            try:
                valvula_id = int(cadastro_raw)
            except (ValueError, TypeError):
                valvula_id = None

        if valvula_id and cliente is not None:
            cadastrada = Valvula.objects.filter(
                pk=valvula_id,
                cliente=cliente,
            ).first()
            valvula_id = cadastrada.pk if cadastrada else None

        if not any(
            [
                numero_serie.strip(),
                tag.strip(),
                diametro.strip(),
                modelo.strip(),
                fabricante.strip(),
                pressao.strip(),
                servico.strip(),
                observacao.strip(),
                valvula_id,
            ]
        ):
            continue

        valvulas.append(
            {
                "item": item,
                "numero_serie": numero_serie,
                "tag": tag,
                "diametro": diametro,
                "modelo": modelo,
                "fabricante": fabricante,
                "pressao_psi": pressao,
                "servico": servico,
                "observacao": observacao,
                "valvula_id": valvula_id,
            }
        )

    return valvulas


def _validar_valvulas_cadastro(cliente, post_data):
    erros = []
    for raw in post_data.getlist("valvula_cadastro[]"):
        if not str(raw).strip():
            continue
        try:
            pk = int(raw)
        except (ValueError, TypeError):
            erros.append("Há uma identificação de válvula cadastrada inválida.")
            continue
        if not Valvula.objects.filter(pk=pk, cliente=cliente).exists():
            erros.append(
                "Não é permitido vincular uma válvula de outro cliente ao relatório."
            )
    return erros


def _salvar_valvulas(relatorio, post_data):
    for dados in _extrair_valvulas_do_post(post_data, cliente=relatorio.cliente):
        ValvulaRelatorio.objects.create(relatorio=relatorio, **dados)


def _substituir_valvulas(relatorio, post_data):
    relatorio.valvulas.all().delete()
    _salvar_valvulas(relatorio, post_data)


class RelatorioTecnicoQuerySetMixin:
    model = RelatorioTecnico

    def get_queryset(self):
        return (
            RelatorioTecnico.objects.select_related("cliente")
            .prefetch_related("valvulas__valvula")
            .order_by("-criado_em")
        )


class RelatorioFormMixin:
    model = RelatorioTecnico
    form_class = RelatorioTecnicoForm
    template_name = "servicos/relatorio_tecnico.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["clientes"] = Cliente.objects.all().order_by("nome")
        form = context.get("form")
        if form is not None:
            context["relatorio"] = form.instance

        if self.request.method == "POST":
            cliente = None
            form = context.get("form")
            if form is not None:
                cliente = form.cleaned_data.get("cliente") if form.is_bound else None
                if cliente is None:
                    cliente = getattr(form.instance, "cliente", None)
            context["valvulas"] = _extrair_valvulas_do_post(
                self.request.POST,
                cliente=cliente,
            )
        elif getattr(self, "object", None) and self.object.pk:
            context["valvulas"] = list(self.object.valvulas.all())
        else:
            context["valvulas"] = []
        return context

    def form_invalid(self, form):
        logger.warning("Formulário de relatório técnico inválido: %s", form.errors)
        messages.error(
            self.request,
            "Não foi possível salvar o relatório. Verifique os campos obrigatórios.",
        )
        return super().form_invalid(form)


class RelatorioValvulaView(LoginRequiredMixin, PermissaoRequeridaMixin, RelatorioFormMixin, CreateView):
    permission_required = "servicos.add_relatoriotecnico"
    def form_valid(self, form):
        erros = _validar_valvulas_cadastro(
            form.cleaned_data["cliente"],
            self.request.POST,
        )
        if erros:
            for erro in erros:
                form.add_error(None, erro)
            return self.form_invalid(form)
        try:
            with transaction.atomic():
                self.object = form.save()
                _salvar_valvulas(self.object, self.request.POST)

            messages.success(
                self.request,
                "Relatório técnico salvo com sucesso!",
            )
            return redirect(self.get_success_url())
        except Exception:
            logger.exception("Erro ao salvar relatório técnico.")
            raise

    def get_success_url(self):
        return reverse("servicos:detalhe_relatorio", args=[self.object.pk])


class RelatorioTecnicoUpdateView(
    LoginRequiredMixin,
    PermissaoRequeridaMixin,
    RelatorioTecnicoQuerySetMixin,
    RelatorioFormMixin,
    UpdateView,
):
    permission_required = "servicos.change_relatoriotecnico"
    def form_valid(self, form):
        erros = _validar_valvulas_cadastro(
            form.cleaned_data["cliente"],
            self.request.POST,
        )
        if erros:
            for erro in erros:
                form.add_error(None, erro)
            return self.form_invalid(form)
        try:
            with transaction.atomic():
                self.object = form.save()
                _substituir_valvulas(self.object, self.request.POST)

            messages.success(
                self.request,
                "Relatório técnico atualizado com sucesso!",
            )
            return redirect(self.get_success_url())
        except Exception:
            logger.exception("Erro ao atualizar relatório técnico.")
            raise

    def get_success_url(self):
        return reverse("servicos:detalhe_relatorio", args=[self.object.pk])


class RelatorioTecnicoDetailView(
    LoginRequiredMixin,
    PermissaoRequeridaMixin,
    RelatorioTecnicoQuerySetMixin,
    DetailView,
):
    permission_required = "servicos.view_relatoriotecnico"
    template_name = "servicos/detalhe_relatorio.html"
    context_object_name = "relatorio"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        relatorio = self.object
        context["cliente"] = relatorio.cliente
        context["valvulas"] = relatorio.valvulas.all()
        context["motivos_relatorio"] = _rotulos_marcados(relatorio, MOTIVOS_RELATORIO)
        context["motivos_reforma"] = _rotulos_marcados(relatorio, MOTIVOS_REFORMA)
        return context


class CertificadoCalibracaoView(
    LoginRequiredMixin,
    PermissaoRequeridaMixin,
    RelatorioTecnicoQuerySetMixin,
    DetailView,
):
    permission_required = "servicos.view_relatoriotecnico"
    template_name = "servicos/certificado_calibracao.html"
    context_object_name = "relatorio"

    def get_object(self, queryset=None):
        return get_object_or_404(
            self.get_queryset(),
            pk=self.kwargs["pk"],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        relatorio = self.object
        context["cliente"] = relatorio.cliente
        context["valvulas"] = relatorio.valvulas.all()
        return context


class OrdensServicoView(LoginRequiredMixin, PermissaoRequeridaMixin, RelatorioTecnicoQuerySetMixin, ListView):
    permission_required = "servicos.view_relatoriotecnico"
    template_name = "servicos/ordens_servico.html"
    context_object_name = "ordens"


class CertificadosListView(LoginRequiredMixin, PermissaoRequeridaMixin, RelatorioTecnicoQuerySetMixin, ListView):
    permission_required = "servicos.view_relatoriotecnico"
    template_name = "servicos/certificados.html"
    context_object_name = "certificados"


class ListaValvulasView(LoginRequiredMixin, PermissaoRequeridaMixin, ListView):
    permission_required = "servicos.view_valvula"
    model = Valvula
    template_name = "servicos/lista_valvulas.html"
    context_object_name = "valvulas"
    paginate_by = 10

    def get_queryset(self):
        queryset = Valvula.objects.select_related("cliente").order_by(
            "cliente__nome",
            "codigo",
        )
        pesquisa = self.request.GET.get("q", "").strip()
        if pesquisa:
            queryset = queryset.filter(
                Q(codigo__icontains=pesquisa)
                | Q(tag__icontains=pesquisa)
                | Q(numero_serie__icontains=pesquisa)
                | Q(fabricante__icontains=pesquisa)
                | Q(modelo__icontains=pesquisa)
                | Q(cliente__nome__icontains=pesquisa)
            )
        cliente_id = self.request.GET.get("cliente", "").strip()
        if cliente_id.isdigit():
            queryset = queryset.filter(cliente_id=int(cliente_id))
        status = self.request.GET.get("status", "").strip()
        if status == "ativa":
            queryset = queryset.filter(ativo=True)
        elif status == "inativa":
            queryset = queryset.filter(ativo=False)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["clientes"] = Cliente.objects.order_by("nome")
        cliente_id = self.request.GET.get("cliente", "").strip()
        context["cliente_filtro"] = (
            Cliente.objects.filter(pk=int(cliente_id)).first()
            if cliente_id.isdigit()
            else None
        )
        return context


class ValvulaCreateView(LoginRequiredMixin, PermissaoRequeridaMixin, CreateView):
    permission_required = "servicos.add_valvula"
    model = Valvula
    form_class = ValvulaForm
    template_name = "servicos/cadastro_valvula.html"

    def get_initial(self):
        initial = super().get_initial()
        cliente_id = self.request.GET.get("cliente", "").strip()
        if cliente_id.isdigit():
            initial["cliente"] = cliente_id
        return initial

    def form_valid(self, form):
        messages.success(self.request, "Válvula cadastrada com sucesso!")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("servicos:detalhe_valvula", args=[self.object.pk])


class ValvulaDetailView(LoginRequiredMixin, PermissaoRequeridaMixin, DetailView):
    permission_required = "servicos.view_valvula"
    model = Valvula
    template_name = "servicos/detalhe_valvula.html"
    context_object_name = "valvula"

    def get_queryset(self):
        return Valvula.objects.select_related("cliente")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["usos_relatorio"] = (
            self.object.itens_relatorio.select_related("relatorio")
            .order_by("-relatorio__criado_em")[:10]
        )
        context.update(historico_valvula(self.object))
        return context


class ValvulaUpdateView(LoginRequiredMixin, PermissaoRequeridaMixin, UpdateView):
    permission_required = "servicos.change_valvula"
    model = Valvula
    form_class = ValvulaForm
    template_name = "servicos/editar_valvula.html"
    context_object_name = "valvula"

    def get_queryset(self):
        return Valvula.objects.select_related("cliente")

    def form_valid(self, form):
        messages.success(self.request, "Válvula atualizada com sucesso!")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("servicos:detalhe_valvula", args=[self.object.pk])


class ValvulaInativarView(LoginRequiredMixin, PermissaoRequeridaMixin, View):
    permission_required = "servicos.change_valvula"
    def post(self, request, pk):
        valvula = get_object_or_404(Valvula, pk=pk)
        valvula.ativo = False
        valvula.save(update_fields=["ativo", "atualizado_em"])
        messages.success(request, "Válvula inativada. O cadastro foi preservado.")
        return redirect("servicos:detalhe_valvula", pk=valvula.pk)


class ValvulasPorClienteJsonView(LoginRequiredMixin, PermissaoRequeridaMixin, View):
    permission_required = "servicos.view_valvula"
    def get(self, request, cliente_id):
        get_object_or_404(Cliente, pk=cliente_id)
        valvulas = (
            Valvula.objects.filter(cliente_id=cliente_id, ativo=True)
            .order_by("codigo")
        )
        dados = [
            {
                "id": valvula.pk,
                "codigo": valvula.codigo,
                "tag": valvula.tag,
                "numero_serie": valvula.numero_serie,
                "fabricante": valvula.fabricante,
                "modelo": valvula.modelo,
                "diametro": valvula.diametro_nominal,
                "pressao": valvula.pressao_formatada,
                "label": str(valvula),
            }
            for valvula in valvulas
        ]
        return JsonResponse({"valvulas": dados})


class ListaInstrumentosView(LoginRequiredMixin, PermissaoRequeridaMixin, ListView):
    permission_required = "servicos.view_instrumento"
    model = Instrumento
    template_name = "servicos/lista_instrumentos.html"
    context_object_name = "instrumentos"
    paginate_by = 10

    def get_queryset(self):
        queryset = Instrumento.objects.select_related("cliente").order_by(
            "cliente__nome",
            "codigo",
        )
        pesquisa = self.request.GET.get("q", "").strip()
        if pesquisa:
            queryset = queryset.filter(
                Q(codigo__icontains=pesquisa)
                | Q(tag__icontains=pesquisa)
                | Q(numero_serie__icontains=pesquisa)
                | Q(fabricante__icontains=pesquisa)
                | Q(modelo__icontains=pesquisa)
                | Q(cliente__nome__icontains=pesquisa)
                | Q(cliente__cnpj__icontains=pesquisa)
            )
        cliente_id = self.request.GET.get("cliente", "").strip()
        if cliente_id.isdigit():
            queryset = queryset.filter(cliente_id=int(cliente_id))
        tipo = self.request.GET.get("tipo", "").strip()
        if tipo:
            queryset = queryset.filter(tipo=tipo)
        status = self.request.GET.get("status", "").strip()
        if status == "ativo":
            queryset = queryset.filter(ativo=True)
        elif status == "inativo":
            queryset = queryset.filter(ativo=False)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["clientes"] = Cliente.objects.order_by("nome")
        context["tipos_instrumento"] = TipoInstrumento.choices
        cliente_id = self.request.GET.get("cliente", "").strip()
        context["cliente_filtro"] = (
            Cliente.objects.filter(pk=int(cliente_id)).first()
            if cliente_id.isdigit()
            else None
        )
        return context


class InstrumentoCreateView(LoginRequiredMixin, PermissaoRequeridaMixin, CreateView):
    permission_required = "servicos.add_instrumento"
    model = Instrumento
    form_class = InstrumentoForm
    template_name = "servicos/cadastro_instrumento.html"

    def get_initial(self):
        initial = super().get_initial()
        cliente_id = self.request.GET.get("cliente", "").strip()
        if cliente_id.isdigit() and Cliente.objects.filter(pk=int(cliente_id)).exists():
            initial["cliente"] = cliente_id
        return initial

    def form_valid(self, form):
        messages.success(self.request, "Instrumento cadastrado com sucesso!")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("servicos:detalhe_instrumento", args=[self.object.pk])


class InstrumentoDetailView(LoginRequiredMixin, PermissaoRequeridaMixin, DetailView):
    permission_required = "servicos.view_instrumento"
    model = Instrumento
    template_name = "servicos/detalhe_instrumento.html"
    context_object_name = "instrumento"

    def get_queryset(self):
        return Instrumento.objects.select_related("cliente").prefetch_related(
            Prefetch(
                "calibracoes",
                queryset=Calibracao.objects.select_related(
                    "certificado",
                    "padrao",
                    "item_ordem_servico",
                    "item_ordem_servico__ordem_servico",
                )
                .annotate(total_pontos=Count("pontos"))
                .order_by("-data_calibracao", "-pk"),
            ),
            Prefetch(
                "itens_ordem_servico",
                queryset=ItemOrdemServico.objects.select_related("ordem_servico"),
            ),
            Prefetch(
                "itens_orcamento",
                queryset=ItemOrcamento.objects.select_related("orcamento").order_by(
                    "-orcamento__data_emissao"
                ),
            ),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(historico_instrumento(self.object))
        vistos = []
        ids = set()
        for item in self.object.itens_orcamento.all():
            if item.orcamento_id not in ids:
                ids.add(item.orcamento_id)
                vistos.append(item.orcamento)
        context["orcamentos_relacionados"] = vistos
        return context


class InstrumentoUpdateView(LoginRequiredMixin, PermissaoRequeridaMixin, UpdateView):
    permission_required = "servicos.change_instrumento"
    model = Instrumento
    form_class = InstrumentoForm
    template_name = "servicos/editar_instrumento.html"
    context_object_name = "instrumento"

    def get_queryset(self):
        return Instrumento.objects.select_related("cliente")

    def form_valid(self, form):
        messages.success(self.request, "Instrumento atualizado com sucesso!")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("servicos:detalhe_instrumento", args=[self.object.pk])


class InstrumentoInativarView(LoginRequiredMixin, PermissaoRequeridaMixin, View):
    permission_required = "servicos.change_instrumento"
    def post(self, request, pk):
        instrumento = get_object_or_404(Instrumento, pk=pk)
        instrumento.ativo = False
        instrumento.save(update_fields=["ativo", "atualizado_em"])
        messages.success(
            request,
            "Instrumento inativado. O cadastro foi preservado.",
        )
        return redirect("servicos:detalhe_instrumento", pk=instrumento.pk)


class ListaPadroesView(LoginRequiredMixin, PermissaoRequeridaMixin, ListView):
    permission_required = "servicos.view_padraomedicao"
    model = PadraoMedicao
    template_name = "servicos/lista_padroes.html"
    context_object_name = "padroes"
    paginate_by = 10

    def get_queryset(self):
        queryset = PadraoMedicao.objects.order_by("codigo")
        pesquisa = self.request.GET.get("q", "").strip()
        if pesquisa:
            queryset = queryset.filter(
                Q(codigo__icontains=pesquisa)
                | Q(identificacao__icontains=pesquisa)
                | Q(fabricante__icontains=pesquisa)
                | Q(modelo__icontains=pesquisa)
                | Q(numero_serie__icontains=pesquisa)
                | Q(numero_certificado__icontains=pesquisa)
            )
        status = self.request.GET.get("status", "").strip()
        if status == "ativo":
            queryset = queryset.filter(ativo=True)
        elif status == "inativo":
            queryset = queryset.filter(ativo=False)
        unidade = self.request.GET.get("unidade", "").strip()
        if unidade:
            queryset = queryset.filter(unidade=unidade)
        fabricante = self.request.GET.get("fabricante", "").strip()
        if fabricante:
            queryset = queryset.filter(fabricante=fabricante)
        validade = self.request.GET.get("validade", "").strip()
        hoje = timezone.localdate()
        if validade == "vigente":
            queryset = queryset.filter(data_validade__gte=hoje)
        elif validade == "vencido":
            queryset = queryset.filter(data_validade__lt=hoje)
        elif validade == "sem_validade":
            queryset = queryset.filter(data_validade__isnull=True)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["unidades"] = UnidadePressao.choices
        context["fabricantes"] = (
            PadraoMedicao.objects.exclude(fabricante="")
            .order_by("fabricante")
            .values_list("fabricante", flat=True)
            .distinct()
        )
        return context


class PadraoCreateView(LoginRequiredMixin, PermissaoRequeridaMixin, CreateView):
    permission_required = "servicos.add_padraomedicao"
    model = PadraoMedicao
    form_class = PadraoMedicaoForm
    template_name = "servicos/cadastro_padrao.html"

    def form_valid(self, form):
        messages.success(self.request, "Padrão de medição cadastrado com sucesso!")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("servicos:detalhe_padrao", args=[self.object.pk])


class PadraoDetailView(LoginRequiredMixin, PermissaoRequeridaMixin, DetailView):
    permission_required = "servicos.view_padraomedicao"
    model = PadraoMedicao
    template_name = "servicos/detalhe_padrao.html"
    context_object_name = "padrao"

    def get_queryset(self):
        return PadraoMedicao.objects.prefetch_related(
            Prefetch(
                "calibracoes",
                queryset=Calibracao.objects.select_related(
                    "instrumento",
                    "instrumento__cliente",
                    "certificado",
                ).order_by("-data_calibracao", "-criado_em"),
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["calibracoes"] = list(self.object.calibracoes.all())
        return context


class PadraoUpdateView(LoginRequiredMixin, PermissaoRequeridaMixin, UpdateView):
    permission_required = "servicos.change_padraomedicao"
    model = PadraoMedicao
    form_class = PadraoMedicaoForm
    template_name = "servicos/editar_padrao.html"
    context_object_name = "padrao"

    def form_valid(self, form):
        messages.success(self.request, "Padrão de medição atualizado com sucesso!")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("servicos:detalhe_padrao", args=[self.object.pk])


class PadraoInativarView(LoginRequiredMixin, PermissaoRequeridaMixin, View):
    permission_required = "servicos.change_padraomedicao"
    def post(self, request, pk):
        padrao = get_object_or_404(PadraoMedicao, pk=pk)
        padrao.ativo = False
        padrao.save(update_fields=["ativo", "atualizado_em"])
        messages.success(
            request,
            "Padrão inativado. O cadastro foi preservado para o histórico.",
        )
        return redirect("servicos:detalhe_padrao", pk=padrao.pk)


def _item_os_do_request(request, calibracao=None):
    if calibracao and calibracao.item_ordem_servico_id:
        return calibracao.item_ordem_servico
    bruto = request.POST.get("item_ordem_servico") or request.GET.get("item", "")
    if str(bruto).isdigit():
        return (
            ItemOrdemServico.objects.select_related(
                "instrumento",
                "ordem_servico",
            )
            .filter(pk=int(bruto))
            .first()
        )
    return None


def _instrumento_para_formset(request, calibracao=None):
    if calibracao and calibracao.instrumento_id:
        return calibracao.instrumento
    item = _item_os_do_request(request, calibracao)
    if item:
        return item.instrumento
    bruto = request.POST.get("instrumento") or request.GET.get("instrumento", "")
    if str(bruto).isdigit():
        return (
            Instrumento.objects.select_related("cliente")
            .filter(pk=int(bruto))
            .first()
        )
    return None


def _montar_formset_pontos(request, calibracao=None):
    instrumento = _instrumento_para_formset(request, calibracao)
    if calibracao is None:
        calibracao = Calibracao()
    kwargs = {
        "instance": calibracao,
        "form_kwargs": {"instrumento": instrumento},
    }
    if request.method == "POST":
        kwargs["data"] = request.POST
    return PontoCalibracaoFormSet(**kwargs)


def _contexto_formulario_calibracao(calibracao=None, item_os=None):
    from .demo_metrologia import CRITERIO_DEMO, PROCEDIMENTO_DEMO_CODIGO

    item = item_os
    if calibracao is not None and getattr(calibracao, "item_ordem_servico_id", None):
        item = calibracao.item_ordem_servico
    if item:
        voltar_url = reverse("servicos:detalhe_item_ordem", args=[item.pk])
    else:
        voltar_url = reverse("servicos:lista_calibracoes")
    procedimentos = [PROCEDIMENTO_DEMO_CODIGO]
    procedimentos.extend(
        Calibracao.objects.exclude(procedimento="")
        .order_by("procedimento")
        .values_list("procedimento", flat=True)
        .distinct()[:15]
    )
    criterios = [CRITERIO_DEMO]
    criterios.extend(
        Calibracao.objects.exclude(criterio_aceitacao="")
        .order_by("criterio_aceitacao")
        .values_list("criterio_aceitacao", flat=True)
        .distinct()[:15]
    )
    return {
        "tem_padrao_disponivel": PadraoMedicao.objects.filter(ativo=True).exists(),
        "procedimentos_sugeridos": list(dict.fromkeys(procedimentos)),
        "criterios_sugeridos": list(dict.fromkeys(criterios)),
        "voltar_url": voltar_url,
    }


class ListaCalibracoesView(LoginRequiredMixin, PermissaoRequeridaMixin, ListView):
    permission_required = "servicos.view_calibracao"
    model = Calibracao
    template_name = "servicos/lista_calibracoes.html"
    context_object_name = "calibracoes"
    paginate_by = 10

    def get_queryset(self):
        queryset = (
            Calibracao.objects.select_related(
                "instrumento",
                "instrumento__cliente",
                "padrao",
            )
            .annotate(total_pontos=Count("pontos"))
            .order_by("-data_calibracao", "-criado_em")
        )
        pesquisa = self.request.GET.get("q", "").strip()
        if pesquisa:
            queryset = queryset.filter(
                Q(numero__icontains=pesquisa)
                | Q(instrumento__codigo__icontains=pesquisa)
                | Q(instrumento__tag__icontains=pesquisa)
                | Q(instrumento__numero_serie__icontains=pesquisa)
                | Q(instrumento__fabricante__icontains=pesquisa)
                | Q(instrumento__cliente__nome__icontains=pesquisa)
            )
        status = self.request.GET.get("status", "").strip()
        if status:
            queryset = queryset.filter(status=status)
        resultado = self.request.GET.get("resultado", "").strip()
        if resultado:
            queryset = queryset.filter(resultado=resultado)
        tipo = self.request.GET.get("tipo", "").strip()
        if tipo:
            queryset = queryset.filter(instrumento__tipo=tipo)
        cliente_id = self.request.GET.get("cliente", "").strip()
        if cliente_id.isdigit():
            queryset = queryset.filter(instrumento__cliente_id=int(cliente_id))
        unidade = self.request.GET.get("unidade", "").strip()
        if unidade:
            queryset = queryset.filter(instrumento__unidade=unidade)
        data_de = self.request.GET.get("data_de", "").strip()
        data_ate = self.request.GET.get("data_ate", "").strip()
        if data_de:
            queryset = queryset.filter(data_calibracao__gte=data_de)
        if data_ate:
            queryset = queryset.filter(data_calibracao__lte=data_ate)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = StatusCalibracao.choices
        context["resultado_choices"] = ResultadoCalibracao.choices
        context["tipos_instrumento"] = TipoInstrumento.choices
        context["unidades"] = UnidadePressao.choices
        context["clientes"] = Cliente.objects.order_by("nome")
        return context


class CalibracaoCreateView(LoginRequiredMixin, PermissaoRequeridaMixin, CreateView):
    permission_required = "servicos.add_calibracao"
    model = Calibracao
    form_class = CalibracaoForm
    template_name = "servicos/cadastro_calibracao.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["item_os"] = _item_os_do_request(self.request)
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        item = _item_os_do_request(self.request)
        if item:
            initial["instrumento"] = item.instrumento_id
            initial["item_ordem_servico"] = item.pk
            return initial
        instrumento_id = self.request.GET.get("instrumento", "").strip()
        if instrumento_id.isdigit():
            instrumento = Instrumento.objects.filter(pk=int(instrumento_id)).first()
            if instrumento:
                initial["instrumento"] = instrumento.pk
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if "formset" not in context:
            context["formset"] = _montar_formset_pontos(self.request, self.object)
        context.update(
            _contexto_formulario_calibracao(
                item_os=_item_os_do_request(self.request)
            )
        )
        return context

    def post(self, request, *args, **kwargs):
        self.object = None
        form = self.get_form()
        formset = _montar_formset_pontos(request)
        if form.is_valid() and formset.is_valid():
            return self.forms_valid(form, formset)
        return self.render_to_response(
            self.get_context_data(form=form, formset=formset)
        )

    def forms_valid(self, form, formset):
        with transaction.atomic():
            self.object = form.save(commit=False)
            self.object.status = StatusCalibracao.RASCUNHO
            self.object.resultado = ResultadoCalibracao.PENDENTE
            self.object.registrar_execucao(self.request.user)
            self.object.atualizar_validade()
            item = self.object.item_ordem_servico
            if item:
                self.object.instrumento = item.instrumento
                item.sincronizar_com_calibracao(self.object)
            self.object.save()
            formset.instance = self.object
            formset.save()
            self.object.aplicar_resultado_oficial()
            self.object.save(update_fields=["resultado", "atualizado_em"])
        messages.success(self.request, "Calibração registrada com sucesso!")
        registrar_auditoria(
            request=self.request,
            acao="CALIBRACAO_CRIADA",
            objeto=self.object,
            descricao=f"Calibração {self.object.numero} criada.",
        )
        return redirect("servicos:detalhe_calibracao", pk=self.object.pk)


class CalibracaoDetailView(LoginRequiredMixin, PermissaoRequeridaMixin, DetailView):
    permission_required = "servicos.view_calibracao"
    model = Calibracao
    template_name = "servicos/detalhe_calibracao.html"
    context_object_name = "calibracao"

    def get_queryset(self):
        return Calibracao.objects.select_related(
            "instrumento",
            "instrumento__cliente",
            "certificado",
            "executor",
            "revisor",
            "padrao",
            "item_ordem_servico",
            "item_ordem_servico__ordem_servico",
        ).prefetch_related("pontos")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["resumo"] = self.object.resumo_aceitacao()
        return context


class CalibracaoUpdateView(LoginRequiredMixin, PermissaoRequeridaMixin, UpdateView):
    permission_required = "servicos.change_calibracao"
    model = Calibracao
    form_class = CalibracaoForm
    template_name = "servicos/editar_calibracao.html"
    context_object_name = "calibracao"

    def get_queryset(self):
        return Calibracao.objects.select_related(
            "instrumento",
            "instrumento__cliente",
            "item_ordem_servico",
        )

    def dispatch(self, request, *args, **kwargs):
        self.request = request
        self.args = args
        self.kwargs = kwargs
        calibracao = self.get_object()
        if not calibracao.pode_editar:
            messages.error(
                request,
                "Calibração concluída ou cancelada não pode ser editada. Reabra o rascunho para alterar.",
            )
            return redirect("servicos:detalhe_calibracao", pk=calibracao.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if "formset" not in context:
            context["formset"] = _montar_formset_pontos(self.request, self.object)
        context.update(_contexto_formulario_calibracao(calibracao=self.object))
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        formset = _montar_formset_pontos(request, self.object)
        if form.is_valid() and formset.is_valid():
            return self.forms_valid(form, formset)
        return self.render_to_response(
            self.get_context_data(form=form, formset=formset)
        )

    def forms_valid(self, form, formset):
        with transaction.atomic():
            self.object = form.save(commit=False)
            self.object.status = StatusCalibracao.RASCUNHO
            self.object.registrar_execucao(self.request.user)
            self.object.atualizar_validade()
            self.object.save()
            formset.instance = self.object
            formset.save()
            self.object.aplicar_resultado_oficial()
            self.object.save(update_fields=["resultado", "atualizado_em"])
        messages.success(self.request, "Calibração atualizada com sucesso!")
        return redirect("servicos:detalhe_calibracao", pk=self.object.pk)


class CalibracaoCancelarView(LoginRequiredMixin, PermissaoRequeridaMixin, View):
    permission_required = "servicos.change_calibracao"
    def post(self, request, pk):
        calibracao = get_object_or_404(
            Calibracao.objects.select_related("instrumento"),
            pk=pk,
        )
        if calibracao.status == StatusCalibracao.CANCELADA:
            messages.info(request, "Esta calibração já estava cancelada.")
        elif not calibracao.pode_cancelar:
            messages.error(
                request,
                "Cancele o certificado emitido antes de cancelar esta calibração.",
            )
        else:
            calibracao.status = StatusCalibracao.CANCELADA
            calibracao.aplicar_resultado_oficial()
            calibracao.save(update_fields=["status", "resultado", "atualizado_em"])
            messages.success(request, "Calibração cancelada. O registro foi preservado.")
        return redirect("servicos:detalhe_calibracao", pk=calibracao.pk)


class CalibracaoConcluirView(LoginRequiredMixin, PermissaoRequeridaMixin, View):
    permission_required = "servicos.concluir_calibracao"
    def post(self, request, pk):
        calibracao = get_object_or_404(
            Calibracao.objects.select_related("instrumento").prefetch_related("pontos"),
            pk=pk,
        )
        if not calibracao.pode_concluir:
            messages.error(request, "Somente calibrações em rascunho podem ser concluídas.")
            return redirect("servicos:detalhe_calibracao", pk=calibracao.pk)
        erros = calibracao.validar_conclusao()
        if erros:
            for erro in erros:
                messages.error(request, erro)
            return redirect("servicos:editar_calibracao", pk=calibracao.pk)
        with transaction.atomic():
            calibracao.status = StatusCalibracao.CONCLUIDA
            calibracao.atualizar_validade()
            calibracao.aplicar_resultado_oficial()
            calibracao.save(
                update_fields=[
                    "status",
                    "resultado",
                    "data_validade",
                    "atualizado_em",
                ]
            )
            if calibracao.item_ordem_servico_id:
                calibracao.item_ordem_servico.sincronizar_com_calibracao(calibracao)
        messages.success(
            request,
            "Calibração concluída. O resultado indica se os pontos atenderam ao critério registrado neste ensaio.",
        )
        registrar_auditoria(
            request=request,
            acao="CALIBRACAO_CONCLUIDA",
            objeto=calibracao,
            descricao=f"Calibração {calibracao.numero} concluída.",
        )
        return redirect("servicos:detalhe_calibracao", pk=calibracao.pk)


class CalibracaoRevisarView(LoginRequiredMixin, PermissaoRequeridaMixin, View):
    permission_required = "servicos.revisar_calibracao"
    def post(self, request, pk):
        calibracao = get_object_or_404(Calibracao, pk=pk)
        if not calibracao.pode_revisar:
            messages.error(
                request,
                "Somente rascunhos ainda não revisados podem receber revisão.",
            )
            return redirect("servicos:detalhe_calibracao", pk=calibracao.pk)
        erros = calibracao.validar_ensaio()
        if erros:
            for erro in erros:
                messages.error(request, erro)
            return redirect("servicos:editar_calibracao", pk=calibracao.pk)
        calibracao.registrar_revisao(request.user)
        calibracao.save(
            update_fields=[
                "executor",
                "executor_nome",
                "executado_em",
                "revisor",
                "revisor_nome",
                "revisado_em",
                "atualizado_em",
            ]
        )
        if calibracao.item_ordem_servico_id:
            calibracao.item_ordem_servico.sincronizar_com_calibracao(calibracao)
        messages.success(
            request,
            "Revisão registrada. A calibração pode ser concluída.",
        )
        registrar_auditoria(
            request=request,
            acao="CALIBRACAO_REVISADA",
            objeto=calibracao,
            descricao=f"Calibração {calibracao.numero} revisada.",
        )
        return redirect("servicos:detalhe_calibracao", pk=calibracao.pk)


class CalibracaoReabrirView(LoginRequiredMixin, PermissaoRequeridaMixin, View):
    permission_required = "servicos.reabrir_calibracao"
    def post(self, request, pk):
        calibracao = get_object_or_404(Calibracao, pk=pk)
        if not calibracao.pode_reabrir:
            messages.error(
                request,
                "Não é possível reabrir esta calibração. Cancele o certificado emitido antes, se houver.",
            )
            return redirect("servicos:detalhe_calibracao", pk=calibracao.pk)
        calibracao.status = StatusCalibracao.RASCUNHO
        calibracao.limpar_revisao()
        calibracao.aplicar_resultado_oficial()
        calibracao.save(
            update_fields=[
                "status",
                "resultado",
                "revisor",
                "revisor_nome",
                "revisado_em",
                "atualizado_em",
            ]
        )
        if calibracao.item_ordem_servico_id:
            calibracao.item_ordem_servico.sincronizar_com_calibracao(calibracao)
        messages.success(request, "Calibração reaberta como rascunho. O resultado voltou a pendente.")
        registrar_auditoria(
            request=request,
            acao="CALIBRACAO_REABERTA",
            objeto=calibracao,
            descricao=f"Calibração {calibracao.numero} reaberta.",
        )
        return redirect("servicos:editar_calibracao", pk=calibracao.pk)


def _queryset_certificados_ensaio():
    return CertificadoCalibracao.objects.select_related(
        "calibracao",
        "calibracao__instrumento",
        "calibracao__instrumento__cliente",
        "calibracao__padrao",
    ).prefetch_related("calibracao__pontos")


class ListaCertificadosEnsaioView(LoginRequiredMixin, PermissaoRequeridaMixin, ListView):
    permission_required = "servicos.view_certificadocalibracao"
    model = CertificadoCalibracao
    template_name = "servicos/lista_certificados_ensaio.html"
    context_object_name = "certificados"
    paginate_by = 10

    def get_queryset(self):
        queryset = _queryset_certificados_ensaio().order_by("-emitido_em", "-criado_em")
        pesquisa = self.request.GET.get("q", "").strip()
        if pesquisa:
            queryset = queryset.filter(
                Q(numero__icontains=pesquisa)
                | Q(calibracao__numero__icontains=pesquisa)
                | Q(calibracao__instrumento__codigo__icontains=pesquisa)
                | Q(calibracao__instrumento__tag__icontains=pesquisa)
                | Q(calibracao__instrumento__numero_serie__icontains=pesquisa)
                | Q(calibracao__instrumento__cliente__nome__icontains=pesquisa)
            )
        status = self.request.GET.get("status", "").strip()
        if status:
            queryset = queryset.filter(status=status)
        resultado = self.request.GET.get("resultado", "").strip()
        if resultado:
            queryset = queryset.filter(calibracao__resultado=resultado)
        cliente_id = self.request.GET.get("cliente", "").strip()
        if cliente_id.isdigit():
            queryset = queryset.filter(
                calibracao__instrumento__cliente_id=int(cliente_id)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = StatusCertificado.choices
        context["resultado_choices"] = ResultadoCalibracao.choices
        context["clientes"] = Cliente.objects.order_by("nome")
        return context


class EmitirCertificadoEnsaioView(LoginRequiredMixin, PermissaoRequeridaMixin, View):
    permission_required = "servicos.emitir_certificado"
    def post(self, request, pk):
        calibracao = get_object_or_404(
            Calibracao.objects.select_related("instrumento", "instrumento__cliente"),
            pk=pk,
        )
        existente = CertificadoCalibracao.objects.filter(calibracao=calibracao).first()
        if existente:
            messages.info(request, "Certificado já emitido.")
            return redirect("servicos:detalhe_certificado", pk=existente.pk)
        if not calibracao.pode_emitir_certificado:
            messages.error(
                request,
                "Só é possível emitir certificado de calibração concluída com resultado aprovado ou reprovado.",
            )
            return redirect("servicos:detalhe_calibracao", pk=calibracao.pk)
        certificado, criado = CertificadoCalibracao.emitir_para(calibracao)
        if certificado is None:
            messages.error(request, "Não foi possível emitir o certificado.")
            return redirect("servicos:detalhe_calibracao", pk=calibracao.pk)
        if criado:
            messages.success(request, "Certificado emitido com sucesso.")
            registrar_auditoria(
                request=request,
                acao="CERTIFICADO_EMITIDO",
                objeto=certificado,
                descricao=f"Certificado {certificado.numero} emitido.",
            )
        else:
            messages.info(request, "Certificado já emitido.")
        return redirect("servicos:detalhe_certificado", pk=certificado.pk)


class CertificadoEnsaioDetailView(LoginRequiredMixin, PermissaoRequeridaMixin, DetailView):
    permission_required = "servicos.view_certificadocalibracao"
    model = CertificadoCalibracao
    template_name = "servicos/detalhe_certificado_ensaio.html"
    context_object_name = "certificado"

    def get_queryset(self):
        return _queryset_certificados_ensaio()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            contexto_documento_certificado(self.object, request=self.request)
        )
        context["modo_impressao"] = False
        return context


class ImprimirCertificadoEnsaioView(CertificadoEnsaioDetailView):
    template_name = "servicos/imprimir_certificado_ensaio.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["modo_impressao"] = True
        return context


class GerarPdfCertificadoEnsaioView(LoginRequiredMixin, PermissaoRequeridaMixin, View):
    permission_required = "servicos.view_certificadocalibracao"
    def get(self, request, pk):
        certificado = get_object_or_404(_queryset_certificados_ensaio(), pk=pk)
        if certificado.calibracao.resultado == ResultadoCalibracao.PENDENTE:
            messages.error(
                request,
                "Não é possível gerar o PDF oficial com resultado pendente.",
            )
            return redirect("servicos:detalhe_certificado", pk=certificado.pk)
        try:
            pdf_bytes = gerar_pdf_certificado(certificado)
        except PdfGenerationError as exc:
            causa = exc.__cause__
            logger.exception(
                "Falha ao gerar PDF do certificado %s (pk=%s, calibração %s, pk_calibracao=%s). "
                "erro=%r causa=%r",
                certificado.numero,
                certificado.pk,
                certificado.calibracao.numero,
                certificado.calibracao_id,
                str(exc),
                str(causa) if causa else None,
            )
            mensagem = "Não foi possível gerar o PDF do certificado. Tente novamente."
            if settings.DEBUG:
                detalhe = str(causa) if causa else str(exc)
                if detalhe:
                    mensagem = f"{mensagem} {detalhe}"
            messages.error(request, mensagem)
            return redirect("servicos:detalhe_certificado", pk=certificado.pk)
        resposta = HttpResponse(pdf_bytes, content_type="application/pdf")
        resposta["Content-Disposition"] = content_disposition_header(
            True,
            nome_arquivo_pdf(certificado.numero),
        )
        return resposta


class CancelarCertificadoEnsaioView(LoginRequiredMixin, PermissaoRequeridaMixin, View):
    permission_required = "servicos.cancelar_certificado"
    def post(self, request, pk):
        certificado = get_object_or_404(CertificadoCalibracao, pk=pk)
        if certificado.pode_cancelar:
            certificado.status = StatusCertificado.CANCELADO
            certificado.save(update_fields=["status", "atualizado_em"])
            messages.success(
                request,
                "Certificado cancelado. O registro foi preservado para auditoria.",
            )
            registrar_auditoria(
                request=request,
                acao="CERTIFICADO_CANCELADO",
                objeto=certificado,
                descricao=f"Certificado {certificado.numero} cancelado.",
            )
        else:
            messages.info(request, "Este certificado já estava cancelado.")
        return redirect("servicos:detalhe_certificado", pk=certificado.pk)


class ValidarCertificadoPublicoView(View):
    def get(self, request, token):
        certificado = (
            CertificadoCalibracao.objects.select_related(
                "calibracao",
                "calibracao__instrumento",
                "calibracao__instrumento__cliente",
            )
            .filter(token_validacao=token)
            .first()
        )
        if certificado is None:
            return render(
                request,
                "servicos/validar_certificado.html",
                {"encontrado": False},
                status=404,
            )
        calibracao = certificado.calibracao
        instrumento = calibracao.instrumento
        if certificado.status == StatusCertificado.CANCELADO:
            situacao = "cancelado"
            rotulo = "CERTIFICADO CANCELADO"
        elif calibracao.validade_expirada:
            situacao = "expirado"
            rotulo = "CERTIFICADO EMITIDO — VALIDADE EXPIRADA"
        else:
            situacao = "valido"
            rotulo = "CERTIFICADO VÁLIDO"
        return render(
            request,
            "servicos/validar_certificado.html",
            {
                "encontrado": True,
                "certificado": certificado,
                "calibracao": calibracao,
                "instrumento": instrumento,
                "situacao": situacao,
                "rotulo_status": rotulo,
            },
        )

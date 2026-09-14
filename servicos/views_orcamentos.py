from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Count, DecimalField, OuterRef, Prefetch, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from acesso.auditoria import registrar_auditoria
from acesso.mixins import PermissaoRequeridaMixin
from clientes.models import Cliente

from .forms import ItemOrcamentoFormSet, OrcamentoForm
from .models import ItemOrcamento, Orcamento, StatusOrcamento
from .operacao import _parse_data, queryset_cobrancas_anotadas


def _formset_itens(request, orcamento=None, cliente=None):
    if orcamento is None:
        orcamento = Orcamento()
    kwargs = {
        "instance": orcamento,
        "cliente": cliente,
        "prefix": "itens",
    }
    if request.method == "POST":
        kwargs["data"] = request.POST
    return ItemOrcamentoFormSet(**kwargs)


def _cliente_do_request(request, orcamento=None):
    if orcamento and orcamento.cliente_id:
        return orcamento.cliente
    bruto = request.POST.get("cliente") or request.GET.get("cliente", "")
    if str(bruto).isdigit():
        return Cliente.objects.filter(pk=int(bruto)).first()
    return None


def aplicar_filtros_orcamentos(queryset, params):
    pesquisa = (params.get("q") or "").strip()
    if pesquisa:
        queryset = queryset.filter(
            Q(numero__icontains=pesquisa)
            | Q(cliente__nome__icontains=pesquisa)
            | Q(cliente__cnpj__icontains=pesquisa)
            | Q(cliente_nome_snapshot__icontains=pesquisa)
            | Q(cliente_documento_snapshot__icontains=pesquisa)
            | Q(itens__instrumento__codigo__icontains=pesquisa)
            | Q(itens__instrumento__tag__icontains=pesquisa)
            | Q(itens__instrumento__numero_serie__icontains=pesquisa)
            | Q(itens__instrumento_codigo_snapshot__icontains=pesquisa)
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
        queryset = queryset.filter(data_emissao__gte=data_de)
    if data_ate:
        queryset = queryset.filter(data_emissao__lte=data_ate)
    return queryset


class ListaOrcamentosView(LoginRequiredMixin, PermissaoRequeridaMixin, ListView):
    permission_required = "servicos.view_orcamento"
    model = Orcamento
    template_name = "servicos/lista_orcamentos.html"
    context_object_name = "orcamentos"
    paginate_by = 10

    def get_queryset(self):
        soma_itens = (
            ItemOrcamento.objects.filter(orcamento_id=OuterRef("pk"))
            .values("orcamento")
            .annotate(s=Sum("total"))
            .values("s")
        )
        queryset = (
            Orcamento.objects.select_related("cliente")
            .prefetch_related("ordens_servico")
            .annotate(
                total_itens=Count("itens", distinct=True),
                total_geral=Coalesce(
                    Subquery(soma_itens),
                    Value(0, output_field=DecimalField(max_digits=12, decimal_places=2)),
                ),
            )
            .order_by("-data_emissao", "-criado_em")
        )
        return aplicar_filtros_orcamentos(queryset, self.request.GET)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = StatusOrcamento.choices
        context["clientes"] = Cliente.objects.order_by("nome")
        return context


class CadastrarOrcamentoView(LoginRequiredMixin, PermissaoRequeridaMixin, CreateView):
    permission_required = "servicos.add_orcamento"
    model = Orcamento
    form_class = OrcamentoForm
    template_name = "servicos/cadastro_orcamento.html"

    def get_initial(self):
        initial = super().get_initial()
        initial["data_emissao"] = timezone.localdate()
        cliente_id = self.request.GET.get("cliente", "").strip()
        if cliente_id.isdigit() and Cliente.objects.filter(pk=int(cliente_id)).exists():
            initial["cliente"] = cliente_id
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cliente = _cliente_do_request(self.request, getattr(self, "object", None))
        if "formset" not in context:
            context["formset"] = _formset_itens(self.request, cliente=cliente)
        return context

    def post(self, request, *args, **kwargs):
        self.object = None
        form = self.get_form()
        cliente = _cliente_do_request(request)
        formset = _formset_itens(request, cliente=cliente)
        if form.is_valid() and formset.is_valid():
            return self.forms_valid(form, formset)
        return self.render_to_response(
            self.get_context_data(form=form, formset=formset)
        )

    def forms_valid(self, form, formset):
        with transaction.atomic():
            dados = form.cleaned_data
            self.object = Orcamento.criar(
                cliente=dados["cliente"],
                data_emissao=dados["data_emissao"],
                data_validade=dados.get("data_validade"),
                condicoes_comerciais=dados.get("condicoes_comerciais") or "",
                observacoes=dados.get("observacoes") or "",
            )
            formset.instance = self.object
            formset.save()
        messages.success(self.request, "Orçamento registrado com sucesso!")
        registrar_auditoria(
            request=self.request,
            acao="ORCAMENTO_CRIADO",
            objeto=self.object,
            descricao=f"Orçamento {self.object.numero} criado.",
        )
        return redirect("servicos:detalhe_orcamento", pk=self.object.pk)


class OrcamentoDetailView(LoginRequiredMixin, PermissaoRequeridaMixin, DetailView):
    permission_required = "servicos.view_orcamento"
    model = Orcamento
    template_name = "servicos/detalhe_orcamento.html"
    context_object_name = "orcamento"

    def get_queryset(self):
        return Orcamento.objects.select_related("cliente").prefetch_related(
            Prefetch(
                "itens",
                queryset=ItemOrcamento.objects.select_related("instrumento", "valvula"),
            ),
            "ordens_servico",
            Prefetch("cobrancas", queryset=queryset_cobrancas_anotadas()),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["totais"] = self.object.totais()
        context["hoje"] = timezone.localdate()
        codigo, rotulo = self.object.situacao_prazo
        context["situacao_prazo_codigo"] = codigo
        context["situacao_prazo_rotulo"] = rotulo
        context["ordem_gerada"] = self.object.ordem_gerada
        context["cobrancas"] = list(self.object.cobrancas.all())
        return context


class EditarOrcamentoView(LoginRequiredMixin, PermissaoRequeridaMixin, UpdateView):
    permission_required = "servicos.change_orcamento"
    model = Orcamento
    form_class = OrcamentoForm
    template_name = "servicos/editar_orcamento.html"
    context_object_name = "orcamento"

    def dispatch(self, request, *args, **kwargs):
        self.request = request
        orcamento = self.get_object()
        if not orcamento.pode_editar:
            messages.error(request, "Somente orçamentos em rascunho podem ser editados.")
            return redirect("servicos:detalhe_orcamento", pk=orcamento.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if "formset" not in context:
            context["formset"] = _formset_itens(
                self.request,
                self.object,
                cliente=self.object.cliente,
            )
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        formset = _formset_itens(request, self.object, cliente=self.object.cliente)
        if form.is_valid() and formset.is_valid():
            return self.forms_valid(form, formset)
        return self.render_to_response(
            self.get_context_data(form=form, formset=formset)
        )

    def forms_valid(self, form, formset):
        with transaction.atomic():
            self.object = form.save(commit=False)
            self.object.aplicar_snapshot_cliente()
            self.object.save()
            formset.instance = self.object
            formset.save()
        messages.success(self.request, "Orçamento atualizado com sucesso!")
        return redirect("servicos:detalhe_orcamento", pk=self.object.pk)


class OrcamentoStatusView(LoginRequiredMixin, PermissaoRequeridaMixin, View):
    acao = None
    permission_map = {
        "enviar": "servicos.enviar_orcamento",
        "aprovar": "servicos.aprovar_orcamento",
        "recusar": "servicos.recusar_orcamento",
        "cancelar": "servicos.cancelar_orcamento",
        "expirar": "servicos.change_orcamento",
        "rascunho": "servicos.change_orcamento",
    }

    def get_permission_required(self):
        return (self.permission_map[self.acao],)

    def post(self, request, pk):
        orcamento = get_object_or_404(Orcamento, pk=pk)
        mapa = {
            "enviar": StatusOrcamento.ENVIADO,
            "aprovar": StatusOrcamento.APROVADO,
            "recusar": StatusOrcamento.RECUSADO,
            "cancelar": StatusOrcamento.CANCELADO,
            "expirar": StatusOrcamento.EXPIRADO,
            "rascunho": StatusOrcamento.RASCUNHO,
        }
        destino = mapa.get(self.acao)
        ok, erro = orcamento.alterar_status(destino)
        if ok:
            messages.success(request, f"Orçamento {orcamento.numero} atualizado.")
            acoes = {
                "enviar": "ORCAMENTO_ENVIADO",
                "aprovar": "ORCAMENTO_APROVADO",
                "recusar": "ORCAMENTO_RECUSADO",
                "cancelar": "ORCAMENTO_CANCELADO",
            }
            registrar_auditoria(
                request=request,
                acao=acoes.get(self.acao, "ORCAMENTO_ATUALIZADO"),
                objeto=orcamento,
                descricao=f"Orçamento {orcamento.numero}: {self.acao}.",
            )
        else:
            messages.error(request, erro)
        return redirect("servicos:detalhe_orcamento", pk=orcamento.pk)


class GerarOrdemServicoView(LoginRequiredMixin, PermissaoRequeridaMixin, View):
    permission_required = "servicos.gerar_ordem_servico"
    def post(self, request, pk):
        orcamento = get_object_or_404(Orcamento, pk=pk)
        ordem, mensagem = orcamento.gerar_ordem_servico()
        if ordem and not mensagem:
            messages.success(request, f"Ordem {ordem.numero} gerada a partir do orçamento.")
            registrar_auditoria(
                request=request,
                acao="ORDEM_SERVICO_GERADA",
                objeto=ordem,
                descricao=f"OS {ordem.numero} gerada a partir de {orcamento.numero}.",
            )
            return redirect("servicos:detalhe_ordem", pk=ordem.pk)
        if ordem:
            messages.info(request, f"OS já gerada: {ordem.numero}")
            return redirect("servicos:detalhe_ordem", pk=ordem.pk)
        messages.error(request, mensagem)
        return redirect("servicos:detalhe_orcamento", pk=orcamento.pk)


class ImprimirOrcamentoView(LoginRequiredMixin, PermissaoRequeridaMixin, DetailView):
    permission_required = "servicos.view_orcamento"
    model = Orcamento
    template_name = "servicos/imprimir_orcamento.html"
    context_object_name = "orcamento"

    def get_queryset(self):
        return Orcamento.objects.select_related("cliente").prefetch_related(
            Prefetch(
                "itens",
                queryset=ItemOrcamento.objects.select_related("instrumento", "valvula"),
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["totais"] = self.object.totais()
        return context

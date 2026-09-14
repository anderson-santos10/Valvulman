from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from acesso.auditoria import registrar_auditoria
from acesso.mixins import PermissaoRequeridaMixin
from clientes.models import Cliente

from .forms import CobrancaForm, PagamentoForm
from .models import (
    Cobranca,
    FormaPagamento,
    Orcamento,
    OrdemServico,
    StatusCobranca,
    StatusOrdemServico,
)
from .operacao import aplicar_filtros_cobrancas, queryset_cobrancas_anotadas


class FinanceiroIndexView(LoginRequiredMixin, PermissaoRequeridaMixin, View):
    permission_required = "servicos.view_cobranca"
    def get(self, request):
        return redirect("servicos:lista_cobrancas")


class ListaCobrancasView(LoginRequiredMixin, PermissaoRequeridaMixin, ListView):
    permission_required = "servicos.view_cobranca"
    model = Cobranca
    template_name = "servicos/financeiro/lista_cobrancas.html"
    context_object_name = "cobrancas"
    paginate_by = 10

    def get_queryset(self):
        queryset = queryset_cobrancas_anotadas().order_by("-data_emissao", "-criado_em")
        return aplicar_filtros_cobrancas(queryset, self.request.GET)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = StatusCobranca.choices
        context["forma_choices"] = FormaPagamento.choices
        context["clientes"] = Cliente.objects.order_by("nome")
        return context


class CadastrarCobrancaView(LoginRequiredMixin, PermissaoRequeridaMixin, CreateView):
    permission_required = "servicos.add_cobranca"
    model = Cobranca
    form_class = CobrancaForm
    template_name = "servicos/financeiro/cadastro_cobranca.html"

    def get_initial(self):
        initial = super().get_initial()
        initial["data_emissao"] = timezone.localdate()
        cliente_id = self.request.GET.get("cliente", "").strip()
        if cliente_id.isdigit() and Cliente.objects.filter(pk=int(cliente_id)).exists():
            initial["cliente"] = cliente_id
        return initial

    def form_valid(self, form):
        dados = form.cleaned_data
        with transaction.atomic():
            self.object = Cobranca.criar(
                cliente=dados["cliente"],
                orcamento=dados.get("orcamento"),
                ordem_servico=dados.get("ordem_servico"),
                descricao=dados["descricao"],
                valor_original=dados["valor_original"],
                desconto=dados.get("desconto") or 0,
                acrescimo=dados.get("acrescimo") or 0,
                data_emissao=dados["data_emissao"],
                data_vencimento=dados["data_vencimento"],
                forma_pagamento=dados.get("forma_pagamento") or "",
                observacoes=dados.get("observacoes") or "",
            )
        messages.success(self.request, f"Cobrança {self.object.numero} registrada.")
        registrar_auditoria(
            request=self.request,
            acao="COBRANCA_CRIADA",
            objeto=self.object,
            descricao=f"Cobrança {self.object.numero} criada.",
        )
        return redirect("servicos:detalhe_cobranca", pk=self.object.pk)


class CobrancaDetailView(LoginRequiredMixin, PermissaoRequeridaMixin, DetailView):
    permission_required = "servicos.view_cobranca"
    model = Cobranca
    template_name = "servicos/financeiro/detalhe_cobranca.html"
    context_object_name = "cobranca"

    def get_queryset(self):
        return Cobranca.objects.select_related(
            "cliente", "orcamento", "ordem_servico"
        ).prefetch_related("pagamentos")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["pagamentos"] = self.object.pagamentos.all()
        context["total_pago"] = self.object.total_pago()
        context["saldo"] = self.object.saldo_devedor()
        context["pagamento_form"] = PagamentoForm(
            cobranca=self.object,
            initial={"data_pagamento": timezone.localdate()},
        )
        return context


class EditarCobrancaView(LoginRequiredMixin, PermissaoRequeridaMixin, UpdateView):
    permission_required = "servicos.change_cobranca"
    model = Cobranca
    form_class = CobrancaForm
    template_name = "servicos/financeiro/editar_cobranca.html"
    context_object_name = "cobranca"

    def dispatch(self, request, *args, **kwargs):
        cobranca = self.get_object()
        if not cobranca.pode_editar:
            messages.error(request, "Somente cobranças pendentes sem pagamento podem ser editadas.")
            return redirect("servicos:detalhe_cobranca", pk=cobranca.pk)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        with transaction.atomic():
            cobranca = form.save(commit=False)
            cobranca.valor_final = cobranca.calcular_valor_final()
            cobranca.full_clean()
            cobranca.save()
        messages.success(self.request, f"Cobrança {cobranca.numero} atualizada.")
        registrar_auditoria(
            request=self.request,
            acao="COBRANCA_EDITADA",
            objeto=cobranca,
            descricao=f"Cobrança {cobranca.numero} editada.",
        )
        return redirect("servicos:detalhe_cobranca", pk=cobranca.pk)


class ImprimirCobrancaView(LoginRequiredMixin, PermissaoRequeridaMixin, DetailView):
    permission_required = "servicos.view_cobranca"
    model = Cobranca
    template_name = "servicos/financeiro/imprimir_cobranca.html"
    context_object_name = "cobranca"

    def get_queryset(self):
        return Cobranca.objects.select_related(
            "cliente", "orcamento", "ordem_servico"
        ).prefetch_related("pagamentos")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["pagamentos"] = self.object.pagamentos.all()
        context["total_pago"] = self.object.total_pago()
        context["saldo"] = self.object.saldo_devedor()
        return context


class CancelarCobrancaView(LoginRequiredMixin, PermissaoRequeridaMixin, View):
    permission_required = "servicos.cancelar_cobranca"
    def get(self, request, pk):
        return HttpResponseNotAllowed(["POST"])

    def post(self, request, pk):
        cobranca = get_object_or_404(Cobranca, pk=pk)
        with transaction.atomic():
            cobranca = Cobranca.objects.select_for_update().get(pk=cobranca.pk)
            ok, erro = cobranca.cancelar()
        if ok:
            messages.success(request, f"Cobrança {cobranca.numero} cancelada.")
            registrar_auditoria(
                request=request,
                acao="COBRANCA_CANCELADA",
                objeto=cobranca,
                descricao=f"Cobrança {cobranca.numero} cancelada.",
            )
        else:
            messages.error(request, erro)
        return redirect("servicos:detalhe_cobranca", pk=cobranca.pk)


class RegistrarPagamentoView(LoginRequiredMixin, PermissaoRequeridaMixin, View):
    permission_required = "servicos.registrar_pagamento"
    def get(self, request, pk):
        return HttpResponseNotAllowed(["POST"])

    def post(self, request, pk):
        cobranca = get_object_or_404(
            Cobranca.objects.select_related("cliente"),
            pk=pk,
        )
        form = PagamentoForm(request.POST, cobranca=cobranca)
        if not cobranca.pode_pagar:
            messages.error(request, "Não é possível registrar pagamento nesta cobrança.")
            return redirect("servicos:detalhe_cobranca", pk=cobranca.pk)
        if not form.is_valid():
            messages.error(request, "Não foi possível registrar o pagamento. Verifique os dados.")
            return render(
                request,
                "servicos/financeiro/detalhe_cobranca.html",
                {
                    "cobranca": cobranca,
                    "pagamentos": cobranca.pagamentos.all(),
                    "total_pago": cobranca.total_pago(),
                    "saldo": cobranca.saldo_devedor(),
                    "pagamento_form": form,
                },
            )
        dados = form.cleaned_data
        try:
            cobranca.registrar_pagamento(
                data_pagamento=dados["data_pagamento"],
                valor=dados["valor"],
                forma_pagamento=dados["forma_pagamento"],
                observacoes=dados.get("observacoes") or "",
            )
            registrar_auditoria(
                request=request,
                acao="PAGAMENTO_REGISTRADO",
                objeto=cobranca,
                descricao=f"Pagamento de R$ {dados['valor']} registrado em {cobranca.numero}.",
            )
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages) if hasattr(exc, "messages") else str(exc))
            return redirect("servicos:detalhe_cobranca", pk=cobranca.pk)
        messages.success(request, "Pagamento registrado.")
        return redirect("servicos:detalhe_cobranca", pk=cobranca.pk)


class GerarCobrancaOrdemView(LoginRequiredMixin, PermissaoRequeridaMixin, View):
    permission_required = "servicos.add_cobranca"
    template_name = "servicos/financeiro/cadastro_cobranca.html"

    def _existente(self, ordem):
        return Cobranca.objects.filter(ordem_servico=ordem).first()

    def get(self, request, pk):
        ordem = get_object_or_404(
            OrdemServico.objects.select_related("cliente", "orcamento"),
            pk=pk,
        )
        existente = self._existente(ordem)
        if existente:
            messages.info(
                request,
                f"Já existe uma cobrança para esta OS. {existente.numero}",
            )
            return redirect("servicos:detalhe_cobranca", pk=existente.pk)
        if ordem.status not in (
            StatusOrdemServico.CONCLUIDA,
            StatusOrdemServico.ENTREGUE,
        ):
            messages.error(request, "Gere a cobrança somente após concluir a OS.")
            return redirect("servicos:detalhe_ordem", pk=ordem.pk)
        valor = Decimal("0.00")
        orcamento = ordem.orcamento
        if orcamento:
            valor = orcamento.totais()["total"]
        form = CobrancaForm(
            initial={
                "cliente": ordem.cliente_id,
                "orcamento": ordem.orcamento_id,
                "ordem_servico": ordem.pk,
                "descricao": f"Serviços da {ordem.numero}",
                "valor_original": valor,
                "desconto": Decimal("0.00"),
                "acrescimo": Decimal("0.00"),
                "data_emissao": timezone.localdate(),
                "data_vencimento": timezone.localdate(),
            }
        )
        return render(
            request,
            self.template_name,
            {"form": form, "ordem_origem": ordem, "geracao_os": True},
        )

    def post(self, request, pk):
        ordem = get_object_or_404(
            OrdemServico.objects.select_related("cliente", "orcamento"),
            pk=pk,
        )
        existente = self._existente(ordem)
        if existente:
            messages.info(
                request,
                f"Já existe uma cobrança para esta OS. {existente.numero}",
            )
            return redirect("servicos:detalhe_cobranca", pk=existente.pk)
        if ordem.status not in (
            StatusOrdemServico.CONCLUIDA,
            StatusOrdemServico.ENTREGUE,
        ):
            messages.error(request, "Gere a cobrança somente após concluir a OS.")
            return redirect("servicos:detalhe_ordem", pk=ordem.pk)
        form = CobrancaForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                {"form": form, "ordem_origem": ordem, "geracao_os": True},
            )
        dados = form.cleaned_data
        if dados["cliente"] != ordem.cliente:
            messages.error(request, "O cliente da cobrança deve ser o da OS.")
            return render(
                request,
                self.template_name,
                {"form": form, "ordem_origem": ordem, "geracao_os": True},
            )
        with transaction.atomic():
            cobranca = Cobranca.criar(
                cliente=ordem.cliente,
                orcamento=ordem.orcamento or dados.get("orcamento"),
                ordem_servico=ordem,
                descricao=dados["descricao"],
                valor_original=dados["valor_original"],
                desconto=dados.get("desconto") or 0,
                acrescimo=dados.get("acrescimo") or 0,
                data_emissao=dados["data_emissao"],
                data_vencimento=dados["data_vencimento"],
                forma_pagamento=dados.get("forma_pagamento") or "",
                observacoes=dados.get("observacoes") or "",
            )
        messages.success(request, f"Cobrança {cobranca.numero} gerada a partir da OS.")
        registrar_auditoria(
            request=request,
            acao="COBRANCA_CRIADA",
            objeto=cobranca,
            descricao=f"Cobrança {cobranca.numero} gerada a partir da OS.",
        )
        return redirect("servicos:detalhe_cobranca", pk=cobranca.pk)


class OrigensFinanceirasJsonView(LoginRequiredMixin, PermissaoRequeridaMixin, View):
    permission_required = "servicos.view_cobranca"
    def get(self, request, cliente_id):
        get_object_or_404(Cliente, pk=cliente_id)
        orcamentos = Orcamento.objects.filter(cliente_id=cliente_id).order_by("-data_emissao")
        ordens = OrdemServico.objects.filter(cliente_id=cliente_id).order_by("-data_entrada")
        return JsonResponse(
            {
                "orcamentos": [
                    {"id": item.pk, "label": item.numero} for item in orcamentos
                ],
                "ordens": [{"id": item.pk, "label": item.numero} for item in ordens],
            }
        )

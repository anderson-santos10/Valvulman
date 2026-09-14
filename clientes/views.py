from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Count, DecimalField, Prefetch, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from acesso.mixins import PermissaoRequeridaMixin
from servicos.models import (
    Calibracao,
    CertificadoCalibracao,
    Instrumento,
    Orcamento,
    OrdemServico,
    RelatorioTecnico,
    Valvula,
)
from servicos.operacao import queryset_cobrancas_anotadas, totais_financeiro_cliente

from .forms import ClienteForm
from .models import Cliente


class ClienteCreateView(LoginRequiredMixin, PermissaoRequeridaMixin, SuccessMessageMixin, CreateView):
    permission_required = "clientes.add_cliente"
    model = Cliente
    form_class = ClienteForm
    template_name = "clientes/cadastro_cliente.html"
    success_message = "Cliente cadastrado com sucesso!"

    def get_success_url(self):
        return reverse("clientes:detalhe_cliente", args=[self.object.pk])


class ListaClientesView(LoginRequiredMixin, PermissaoRequeridaMixin, ListView):
    permission_required = "clientes.view_cliente"
    model = Cliente
    template_name = "clientes/lista_clientes.html"
    context_object_name = "clientes"
    ordering = ["nome"]
    paginate_by = 10

    def get_queryset(self):
        queryset = super().get_queryset()
        pesquisa = self.request.GET.get("q", "").strip()

        if pesquisa:
            queryset = queryset.filter(
                Q(nome__icontains=pesquisa)
                | Q(cnpj__icontains=pesquisa)
                | Q(cep__icontains=pesquisa)
                | Q(endereco__icontains=pesquisa)
                | Q(contato_principal__icontains=pesquisa)
                | Q(telefone__icontains=pesquisa)
                | Q(email__icontains=pesquisa)
            )

        return queryset.order_by("nome")


class ClienteDetailView(LoginRequiredMixin, PermissaoRequeridaMixin, DetailView):
    permission_required = "clientes.view_cliente"
    model = Cliente
    template_name = "clientes/detalhe_cliente.html"
    context_object_name = "cliente"

    def get_queryset(self):
        return Cliente.objects.prefetch_related(
            Prefetch(
                "valvulas",
                queryset=Valvula.objects.order_by("codigo"),
            ),
            Prefetch(
                "instrumentos",
                queryset=Instrumento.objects.annotate(
                    total_calibracoes=Count("calibracoes")
                ).order_by("codigo"),
            ),
            Prefetch(
                "relatorios_tecnicos",
                queryset=RelatorioTecnico.objects.prefetch_related("valvulas").order_by(
                    "-criado_em"
                ),
            ),
            Prefetch(
                "ordens_servico",
                queryset=OrdemServico.objects.annotate(
                    total_itens=Count("itens")
                ).order_by("-data_entrada", "-criado_em"),
            ),
            Prefetch(
                "orcamentos",
                queryset=Orcamento.objects.prefetch_related("ordens_servico").annotate(
                    total_geral=Coalesce(
                        Sum("itens__total"),
                        Value(0, output_field=DecimalField(max_digits=12, decimal_places=2)),
                    )
                ).order_by("-data_emissao", "-criado_em"),
            ),
            Prefetch(
                "cobrancas",
                queryset=queryset_cobrancas_anotadas().order_by(
                    "-data_emissao", "-criado_em"
                ),
            ),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        valvulas = list(self.object.valvulas.all())
        ativas = [valvula for valvula in valvulas if valvula.ativo]
        inativas = [valvula for valvula in valvulas if not valvula.ativo]
        context["valvulas_ativas"] = ativas
        context["valvulas_inativas"] = inativas
        context["total_valvulas"] = len(valvulas)
        context["total_valvulas_ativas"] = len(ativas)
        context["total_valvulas_inativas"] = len(inativas)
        instrumentos = list(self.object.instrumentos.all())
        instrumentos_ativos = [
            instrumento for instrumento in instrumentos if instrumento.ativo
        ]
        instrumentos_inativos = [
            instrumento for instrumento in instrumentos if not instrumento.ativo
        ]
        context["instrumentos_ativos"] = instrumentos_ativos
        context["instrumentos_inativos"] = instrumentos_inativos
        context["total_instrumentos"] = len(instrumentos)
        context["total_instrumentos_ativos"] = len(instrumentos_ativos)
        context["total_instrumentos_inativos"] = len(instrumentos_inativos)
        context["relatorios"] = list(self.object.relatorios_tecnicos.all())
        context["ordens"] = list(self.object.ordens_servico.all())
        context["orcamentos"] = list(self.object.orcamentos.all())
        if self.request.user.has_perm("servicos.view_cobranca"):
            context["cobrancas"] = list(self.object.cobrancas.all())
            context["financeiro"] = totais_financeiro_cliente(self.object)
        else:
            context["cobrancas"] = []
            context["financeiro"] = None
        context["total_calibracoes"] = Calibracao.objects.filter(
            instrumento__cliente=self.object
        ).count()
        context["total_certificados"] = CertificadoCalibracao.objects.filter(
            calibracao__instrumento__cliente=self.object
        ).count()
        return context


class ClienteUpdateView(LoginRequiredMixin, PermissaoRequeridaMixin, SuccessMessageMixin, UpdateView):
    permission_required = "clientes.change_cliente"
    model = Cliente
    form_class = ClienteForm
    template_name = "clientes/editar_cliente.html"
    success_message = "Cliente atualizado com sucesso!"

    def get_success_url(self):
        return reverse("clientes:detalhe_cliente", args=[self.object.pk])
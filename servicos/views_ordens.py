from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from acesso.auditoria import registrar_auditoria
from acesso.mixins import PermissaoRequeridaMixin
from clientes.models import Cliente

from .forms import (
    ItemOrdemServicoFormSet,
    OrdemServicoForm,
)
from .models import (
    Calibracao,
    ExecucaoValvula,
    Instrumento,
    ItemOrdemServico,
    OrdemServico,
    ServicoSolicitado,
    StatusCalibracao,
    StatusItemOrdem,
    StatusOrdemServico,
    SUGESTOES_CONDICAO_RECEBIMENTO,
    Valvula,
)
from .operacao import aplicar_filtros_lista_ordens, fila_ordens, queryset_cobrancas_anotadas


def _formset_itens(request, ordem=None, cliente=None):
    if ordem is None:
        ordem = OrdemServico()
    kwargs = {
        "instance": ordem,
        "cliente": cliente,
        "prefix": "itens",
    }
    if request.method == "POST":
        kwargs["data"] = request.POST
    return ItemOrdemServicoFormSet(**kwargs)


def _cliente_do_request(request, ordem=None):
    if ordem and ordem.cliente_id:
        return ordem.cliente
    bruto = request.POST.get("cliente") or request.GET.get("cliente", "")
    if str(bruto).isdigit():
        return Cliente.objects.filter(pk=int(bruto)).first()
    return None


class ListaOrdensServicoLabView(LoginRequiredMixin, PermissaoRequeridaMixin, ListView):
    permission_required = "servicos.view_ordemservico"
    model = OrdemServico
    template_name = "servicos/lista_ordens.html"
    context_object_name = "ordens"
    paginate_by = 10

    def get_queryset(self):
        queryset = OrdemServico.objects.select_related("cliente").annotate(
            total_itens=Count("itens")
        ).order_by("-data_entrada", "-criado_em")
        return aplicar_filtros_lista_ordens(queryset, self.request.GET)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = StatusOrdemServico.choices
        context["clientes"] = Cliente.objects.order_by("nome")
        return context


class OrdemServicoCreateView(LoginRequiredMixin, PermissaoRequeridaMixin, CreateView):
    permission_required = "servicos.add_ordemservico"
    model = OrdemServico
    form_class = OrdemServicoForm
    template_name = "servicos/cadastro_ordem.html"

    def get_initial(self):
        initial = super().get_initial()
        cliente_id = self.request.GET.get("cliente", "").strip()
        if cliente_id.isdigit():
            cliente = Cliente.objects.filter(pk=int(cliente_id)).first()
            if cliente:
                initial["cliente"] = cliente.pk
                contato = cliente.dados_contato()
                initial["solicitante"] = contato["contato_principal"]
                initial["telefone_solicitante"] = contato["telefone"]
                initial["email_solicitante"] = contato["email"]
                initial["contato_solicitante"] = (
                    contato["telefone"] or contato["email"]
                )
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cliente = _cliente_do_request(self.request, getattr(self, "object", None))
        if "formset" not in context:
            context["formset"] = _formset_itens(self.request, cliente=cliente)
        context["sugestoes_condicao"] = SUGESTOES_CONDICAO_RECEBIMENTO
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
            self.object = OrdemServico.criar(
                cliente=dados["cliente"],
                data_entrada=dados["data_entrada"],
                data_previsao_entrega=dados.get("data_previsao_entrega"),
                solicitante=dados.get("solicitante") or "",
                contato_solicitante=dados.get("contato_solicitante") or "",
                telefone_solicitante=dados.get("telefone_solicitante") or "",
                email_solicitante=dados.get("email_solicitante") or "",
                responsavel_recebimento=dados.get("responsavel_recebimento") or "",
                observacoes=dados.get("observacoes") or "",
            )
            formset.instance = self.object
            formset.save()
            self.object.refresh_from_db()
            self.object.alterar_status(StatusOrdemServico.RECEBIDA)
        messages.success(self.request, "Ordem de serviço recebida com sucesso!")
        registrar_auditoria(
            request=self.request,
            acao="ORDEM_SERVICO_CRIADA",
            objeto=self.object,
            descricao=f"Ordem {self.object.numero} criada e recebida.",
        )
        return redirect("servicos:detalhe_ordem", pk=self.object.pk)


class OrdemServicoDetailView(LoginRequiredMixin, PermissaoRequeridaMixin, DetailView):
    permission_required = "servicos.view_ordemservico"
    model = OrdemServico
    template_name = "servicos/detalhe_ordem.html"
    context_object_name = "ordem"

    def get(self, request, *args, **kwargs):
        self.object = super().get_object()
        self.object.sincronizar_status_pelos_itens()
        self.object.refresh_from_db()
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def get_queryset(self):
        return OrdemServico.objects.select_related("cliente", "orcamento").prefetch_related(
            Prefetch(
                "itens",
                queryset=ItemOrdemServico.objects.select_related(
                    "instrumento",
                    "instrumento__cliente",
                    "valvula",
                    "valvula__cliente",
                    "execucao_valvula",
                ).prefetch_related(
                    Prefetch(
                        "calibracoes",
                        queryset=Calibracao.objects.select_related("certificado"),
                    )
                ),
            ),
            Prefetch("cobrancas", queryset=queryset_cobrancas_anotadas()),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["hoje"] = timezone.localdate()
        context["progresso"] = self.object.resumo_progresso()
        context["situacao_prazo_codigo"], context["situacao_prazo_rotulo"] = (
            self.object.situacao_prazo
        )
        context["cobrancas"] = list(self.object.cobrancas.all())
        context["proximo_passo"] = self.object.proximo_passo()
        context["composicao_servicos"] = [
            {
                "rotulo": ServicoSolicitado(codigo).label,
                "quantidade": quantidade,
            }
            for codigo, quantidade in context["progresso"]["servicos"].items()
        ]
        return context


class OrdemServicoUpdateView(LoginRequiredMixin, PermissaoRequeridaMixin, UpdateView):
    permission_required = "servicos.change_ordemservico"
    model = OrdemServico
    form_class = OrdemServicoForm
    template_name = "servicos/editar_ordem.html"
    context_object_name = "ordem"

    def dispatch(self, request, *args, **kwargs):
        self.request = request
        ordem = self.get_object()
        if not ordem.pode_editar:
            messages.error(
                request,
                "Ordens entregues ou canceladas não podem ser editadas.",
            )
            return redirect("servicos:detalhe_ordem", pk=ordem.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if "formset" not in context:
            context["formset"] = _formset_itens(
                self.request,
                self.object,
                cliente=self.object.cliente,
            )
        context["sugestoes_condicao"] = SUGESTOES_CONDICAO_RECEBIMENTO
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
            self.object = form.save()
            formset.instance = self.object
            formset.save()
        messages.success(self.request, "Ordem de serviço atualizada com sucesso!")
        return redirect("servicos:detalhe_ordem", pk=self.object.pk)


class OrdemServicoStatusView(LoginRequiredMixin, PermissaoRequeridaMixin, View):
    acao = None
    permission_map = {
        "receber": "servicos.receber_ordem",
        "iniciar": "servicos.iniciar_ordem",
        "revisao": "servicos.revisar_ordem",
        "concluir": "servicos.concluir_ordem",
        "entregar": "servicos.entregar_ordem",
        "cancelar": "servicos.cancelar_ordem",
    }

    def get_permission_required(self):
        return (self.permission_map[self.acao],)

    def post(self, request, pk):
        ordem = get_object_or_404(OrdemServico, pk=pk)
        mapa = {
            "receber": StatusOrdemServico.RECEBIDA,
            "iniciar": StatusOrdemServico.EM_EXECUCAO,
            "revisao": StatusOrdemServico.AGUARDANDO_REVISAO,
            "concluir": StatusOrdemServico.CONCLUIDA,
            "entregar": StatusOrdemServico.ENTREGUE,
            "cancelar": StatusOrdemServico.CANCELADA,
        }
        destino = mapa.get(self.acao)
        ok, erro = ordem.alterar_status(destino)
        if ok:
            messages.success(request, f"Ordem {ordem.numero} atualizada.")
            acoes = {
                "receber": "ORDEM_SERVICO_RECEBIDA",
                "iniciar": "ORDEM_SERVICO_INICIADA",
                "revisao": "ORDEM_SERVICO_REVISAO",
                "concluir": "ORDEM_SERVICO_CONCLUIDA",
                "entregar": "ORDEM_SERVICO_ENTREGUE",
                "cancelar": "ORDEM_SERVICO_CANCELADA",
            }
            registrar_auditoria(
                request=request,
                acao=acoes.get(self.acao, "ORDEM_SERVICO_ATUALIZADA"),
                objeto=ordem,
                descricao=f"Ordem {ordem.numero}: {self.acao}.",
            )
        else:
            messages.error(request, erro)
        return redirect("servicos:detalhe_ordem", pk=ordem.pk)


class OrdemServicoImprimirView(LoginRequiredMixin, PermissaoRequeridaMixin, DetailView):
    permission_required = "servicos.view_ordemservico"
    model = OrdemServico
    template_name = "servicos/imprimir_ordem.html"
    context_object_name = "ordem"

    def get_queryset(self):
        return OrdemServico.objects.select_related("cliente").prefetch_related(
            Prefetch(
                "itens",
                queryset=ItemOrdemServico.objects.select_related(
                    "instrumento",
                    "valvula",
                ),
            )
        )


class ItemVincularCalibracaoView(LoginRequiredMixin, PermissaoRequeridaMixin, View):
    permission_required = "servicos.change_ordemservico"
    def post(self, request, pk):
        item = get_object_or_404(
            ItemOrdemServico.objects.select_related("instrumento", "ordem_servico"),
            pk=pk,
        )
        if not item.ordem_servico.pode_editar:
            messages.error(request, "Esta ordem de serviço não pode mais ser alterada.")
            return redirect("servicos:detalhe_ordem", pk=item.ordem_servico_id)
        bruto = request.POST.get("calibracao", "").strip()
        calibracao = None
        if bruto.isdigit():
            calibracao = Calibracao.objects.select_related("instrumento").filter(
                pk=int(bruto)
            ).first()
        if calibracao is None:
            messages.error(request, "Calibração não encontrada.")
            return redirect("servicos:detalhe_ordem", pk=item.ordem_servico_id)
        if calibracao.instrumento_id != item.instrumento_id:
            messages.error(
                request,
                "A calibração deve pertencer ao mesmo instrumento do item.",
            )
            return redirect("servicos:detalhe_ordem", pk=item.ordem_servico_id)
        calibracao.item_ordem_servico = item
        try:
            calibracao.full_clean()
            calibracao.save(update_fields=["item_ordem_servico", "atualizado_em"])
            item.sincronizar_com_calibracao(calibracao)
        except ValidationError:
            messages.error(request, "Não foi possível vincular esta calibração.")
            return redirect("servicos:detalhe_ordem", pk=item.ordem_servico_id)
        messages.success(request, f"Calibração {calibracao.numero} vinculada ao item.")
        return redirect("servicos:detalhe_item_ordem", pk=item.pk)


class ItemOrdemServicoDetailView(LoginRequiredMixin, PermissaoRequeridaMixin, DetailView):
    permission_required = "servicos.view_ordemservico"
    model = ItemOrdemServico
    template_name = "servicos/detalhe_item_ordem.html"
    context_object_name = "item"

    def get(self, request, *args, **kwargs):
        self.object = super().get_object()
        self.object.ordem_servico.sincronizar_status_pelos_itens()
        self.object.refresh_from_db()
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def get_queryset(self):
        return ItemOrdemServico.objects.select_related(
            "ordem_servico",
            "ordem_servico__cliente",
            "instrumento",
            "valvula",
            "execucao_valvula",
        ).prefetch_related(
            Prefetch(
                "calibracoes",
                queryset=Calibracao.objects.select_related("certificado").order_by(
                    "-criado_em"
                ),
            )
        )


class ItemOrdemServicoStatusView(LoginRequiredMixin, PermissaoRequeridaMixin, View):
    acao = None
    permission_map = {
        "iniciar": "servicos.iniciar_ordem",
        "revisao": "servicos.revisar_ordem",
        "concluir": "servicos.concluir_ordem",
        "cancelar": "servicos.cancelar_ordem",
    }

    def get_permission_required(self):
        return (self.permission_map[self.acao],)

    def post(self, request, pk):
        item = get_object_or_404(
            ItemOrdemServico.objects.select_related(
                "ordem_servico",
                "instrumento",
                "valvula",
            ),
            pk=pk,
        )
        ordem = item.ordem_servico
        if ordem.status in (
            StatusOrdemServico.ENTREGUE,
            StatusOrdemServico.CANCELADA,
        ):
            messages.error(request, "Esta ordem de serviço não pode mais ser alterada.")
            return redirect("servicos:detalhe_item_ordem", pk=item.pk)
        mapa = {
            "iniciar": StatusItemOrdem.EM_EXECUCAO,
            "revisao": StatusItemOrdem.AGUARDANDO_REVISAO,
            "concluir": StatusItemOrdem.CONCLUIDO,
            "cancelar": StatusItemOrdem.CANCELADO,
        }
        destino = mapa.get(self.acao)
        if destino is None:
            messages.error(request, "Ação inválida para o item.")
            return redirect("servicos:detalhe_item_ordem", pk=item.pk)
        if item.exige_calibracao and self.acao == "iniciar":
            try:
                calibracao, criada = Calibracao.abrir_para_item(item, request.user)
            except ValidationError as exc:
                texto = " ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
                messages.error(request, texto)
                return redirect("servicos:detalhe_item_ordem", pk=item.pk)
            registrar_auditoria(
                request=request,
                acao="ITEM_OS_INICIAR",
                objeto=ordem,
                descricao=f"Item {item.codigo_equipamento} da {ordem.numero}: {self.acao}.",
            )
            if criada:
                messages.success(
                    request,
                    f"Calibração de {item.codigo_equipamento} iniciada.",
                )
            else:
                messages.info(
                    request,
                    f"A calibração de {item.codigo_equipamento} já estava iniciada.",
                )
            if calibracao.pode_editar:
                return redirect("servicos:editar_calibracao", pk=calibracao.pk)
            return redirect("servicos:detalhe_calibracao", pk=calibracao.pk)
        if item.eh_valvula and self.acao == "iniciar":
            try:
                ExecucaoValvula.abrir_para_item(item, request.user)
            except ValidationError as exc:
                texto = " ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
                messages.error(request, texto)
                return redirect("servicos:detalhe_item_ordem", pk=item.pk)
            registrar_auditoria(
                request=request,
                acao="ITEM_OS_INICIAR",
                objeto=ordem,
                descricao=f"Item {item.codigo_equipamento} da {ordem.numero}: {self.acao}.",
            )
            messages.success(request, f"Execução de {item.codigo_equipamento} aberta.")
            return redirect("servicos:detalhe_execucao_valvula", pk=item.pk)
        if item.eh_valvula and destino == StatusItemOrdem.AGUARDANDO_REVISAO:
            execucao = item.execucao_valvula_atual
            if execucao is None:
                messages.error(
                    request,
                    "Abra a execução da válvula antes de enviar o item para revisão.",
                )
                return redirect("servicos:detalhe_item_ordem", pk=item.pk)
            erros = execucao.validar_envio_revisao()
            if erros:
                messages.error(request, erros[0])
                return redirect("servicos:detalhe_execucao_valvula", pk=item.pk)
        if destino == StatusItemOrdem.CONCLUIDO and not item.pode_concluir_item():
            if item.eh_valvula:
                messages.error(
                    request,
                    "Conclua a execução desta válvula (com resultado e revisão) antes de concluir o item.",
                )
            else:
                messages.error(
                    request,
                    "Conclua a calibração deste manômetro antes de concluir o item.",
                )
            return redirect("servicos:detalhe_item_ordem", pk=item.pk)
        item.aplicar_status(destino)
        registrar_auditoria(
            request=request,
            acao=f"ITEM_OS_{self.acao.upper()}",
            objeto=ordem,
            descricao=f"Item {item.codigo_equipamento} da {ordem.numero}: {self.acao}.",
        )
        messages.success(request, f"Item {item.codigo_equipamento} atualizado.")
        return redirect("servicos:detalhe_item_ordem", pk=item.pk)


class FilaOrdensView(LoginRequiredMixin, PermissaoRequeridaMixin, TemplateView):
    permission_required = "servicos.view_ordemservico"
    template_name = "servicos/fila_ordens.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from .operacao import fila_itens

        context.update(fila_ordens())
        context.update(fila_itens())
        context["hoje"] = timezone.localdate()
        return context


class InstrumentosPorClienteJsonView(LoginRequiredMixin, PermissaoRequeridaMixin, View):
    permission_required = "servicos.view_ordemservico"

    def get(self, request, cliente_id):
        cliente = get_object_or_404(Cliente, pk=cliente_id)
        instrumentos = Instrumento.objects.filter(
            cliente_id=cliente_id, ativo=True
        ).order_by("codigo")
        valvulas = Valvula.objects.filter(cliente_id=cliente_id, ativo=True).order_by(
            "codigo"
        )
        return JsonResponse(
            {
                "cliente": {
                    "id": cliente.pk,
                    **cliente.dados_contato(),
                },
                "instrumentos": [
                    {
                        "id": instrumento.pk,
                        "codigo": instrumento.codigo,
                        "tag": instrumento.tag,
                        "numero_serie": instrumento.numero_serie,
                        "label": (
                            f"{instrumento.codigo} — "
                            f"{instrumento.tag or instrumento.numero_serie or instrumento.modelo or instrumento.codigo}"
                        ),
                    }
                    for instrumento in instrumentos
                ],
                "valvulas": [
                    {
                        "id": valvula.pk,
                        "codigo": valvula.codigo,
                        "tag": valvula.tag,
                        "numero_serie": valvula.numero_serie,
                        "label": (
                            f"{valvula.codigo} — "
                            f"{valvula.tag or valvula.numero_serie or valvula.modelo or valvula.codigo}"
                        ),
                    }
                    for valvula in valvulas
                ],
            }
        )

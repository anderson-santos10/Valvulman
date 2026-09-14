from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from acesso.auditoria import registrar_auditoria
from acesso.mixins import PermissaoRequeridaMixin

from .forms import ExecucaoValvulaForm
from .models import (
    ExecucaoValvula,
    ItemOrdemServico,
    StatusExecucaoValvula,
    StatusItemOrdem,
    StatusOrdemServico,
)


def _item_valvula_ou_invalido(pk):
    item = get_object_or_404(
        ItemOrdemServico.objects.select_related(
            "ordem_servico",
            "ordem_servico__cliente",
            "valvula",
            "valvula__cliente",
        ),
        pk=pk,
    )
    if not item.eh_valvula or not item.valvula_id:
        return None, item
    return item, None


def _ordem_bloqueada(item):
    return item.ordem_servico.status in (
        StatusOrdemServico.ENTREGUE,
        StatusOrdemServico.CANCELADA,
    )


def _render_execucao(request, item, execucao, form):
    return render(
        request,
        "servicos/execucao_valvula.html",
        {
            "item": item,
            "execucao": execucao,
            "ordem": item.ordem_servico,
            "form": form,
        },
    )


class ExecucaoValvulaAbrirView(LoginRequiredMixin, PermissaoRequeridaMixin, View):
    permission_required = "servicos.iniciar_ordem"

    def post(self, request, pk):
        item, invalido = _item_valvula_ou_invalido(pk)
        if invalido is not None:
            messages.error(
                request,
                "A execução de válvula só pode ser aberta para um item de válvula.",
            )
            return redirect("servicos:detalhe_item_ordem", pk=invalido.pk)
        if _ordem_bloqueada(item):
            messages.error(request, "Esta ordem de serviço não pode mais ser alterada.")
            return redirect("servicos:detalhe_item_ordem", pk=item.pk)
        try:
            execucao, criada = ExecucaoValvula.abrir_para_item(item, request.user)
        except ValidationError as exc:
            texto = " ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
            messages.error(request, texto)
            return redirect("servicos:detalhe_item_ordem", pk=item.pk)
        if criada:
            registrar_auditoria(
                request=request,
                acao="EXECUCAO_VALVULA_ABERTA",
                objeto=execucao,
                descricao=(
                    f"Execução aberta para {item.codigo_equipamento} "
                    f"na {item.ordem_servico.numero}."
                ),
            )
            messages.success(request, "Execução de válvula aberta em rascunho.")
        return redirect("servicos:detalhe_execucao_valvula", pk=item.pk)


class ExecucaoValvulaDetailView(LoginRequiredMixin, PermissaoRequeridaMixin, View):
    permission_required = "servicos.view_ordemservico"

    def get(self, request, pk):
        item, invalido = _item_valvula_ou_invalido(pk)
        if invalido is not None:
            messages.error(
                request,
                "Este item não é uma válvula e não possui execução de válvula.",
            )
            return redirect("servicos:detalhe_item_ordem", pk=invalido.pk)
        execucao = item.execucao_valvula_atual
        if execucao is None:
            messages.info(
                request,
                "Abra a execução para registrar o serviço desta válvula.",
            )
            return redirect("servicos:detalhe_item_ordem", pk=item.pk)
        form = ExecucaoValvulaForm(
            instance=execucao,
            somente_revisao=execucao.pode_revisar and not execucao.pode_editar,
        )
        return _render_execucao(request, item, execucao, form)


class ExecucaoValvulaSalvarView(LoginRequiredMixin, PermissaoRequeridaMixin, View):
    permission_required = "servicos.change_ordemservico"

    def post(self, request, pk):
        item, invalido = _item_valvula_ou_invalido(pk)
        if invalido is not None:
            messages.error(
                request,
                "A execução de válvula só existe para itens de válvula.",
            )
            return redirect("servicos:detalhe_item_ordem", pk=invalido.pk)
        execucao = item.execucao_valvula_atual
        if execucao is None:
            messages.error(request, "Abra a execução antes de salvar.")
            return redirect("servicos:detalhe_item_ordem", pk=item.pk)
        if _ordem_bloqueada(item) or not execucao.pode_editar:
            messages.error(request, "Esta execução não pode ser editada no estado atual.")
            return redirect("servicos:detalhe_execucao_valvula", pk=item.pk)
        form = ExecucaoValvulaForm(request.POST, instance=execucao)
        if not form.is_valid():
            return _render_execucao(request, item, execucao, form)
        with transaction.atomic():
            execucao = form.save(commit=False)
            execucao.status = StatusExecucaoValvula.RASCUNHO
            execucao.registrar_execucao(request.user)
            execucao.save()
            item.sincronizar_com_execucao_valvula(execucao)
        messages.success(request, "Rascunho da execução salvo.")
        return redirect("servicos:detalhe_execucao_valvula", pk=item.pk)


class ExecucaoValvulaEnviarRevisaoView(LoginRequiredMixin, PermissaoRequeridaMixin, View):
    permission_required = "servicos.revisar_ordem"

    def post(self, request, pk):
        item, invalido = _item_valvula_ou_invalido(pk)
        if invalido is not None:
            messages.error(
                request,
                "A execução de válvula só existe para itens de válvula.",
            )
            return redirect("servicos:detalhe_item_ordem", pk=invalido.pk)
        execucao = item.execucao_valvula_atual
        if execucao is None:
            messages.error(request, "Abra a execução antes de enviar para revisão.")
            return redirect("servicos:detalhe_item_ordem", pk=item.pk)
        if _ordem_bloqueada(item) or not execucao.pode_enviar_revisao:
            messages.error(request, "Esta execução não pode ser enviada para revisão.")
            return redirect("servicos:detalhe_execucao_valvula", pk=item.pk)
        form = ExecucaoValvulaForm(request.POST, instance=execucao)
        if not form.is_valid():
            return _render_execucao(request, item, execucao, form)
        execucao = form.save(commit=False)
        execucao.status = StatusExecucaoValvula.RASCUNHO
        execucao.registrar_execucao(request.user)
        erros = execucao.validar_envio_revisao()
        if erros:
            for erro in erros:
                messages.error(request, erro)
            return _render_execucao(request, item, execucao, form)
        with transaction.atomic():
            execucao.save()
            item.aplicar_status(StatusItemOrdem.AGUARDANDO_REVISAO)
        registrar_auditoria(
            request=request,
            acao="EXECUCAO_VALVULA_REVISAO",
            objeto=execucao,
            descricao=(
                f"Execução de {item.codigo_equipamento} enviada para revisão "
                f"na {item.ordem_servico.numero}."
            ),
        )
        messages.success(request, "Execução enviada para revisão.")
        return redirect("servicos:detalhe_execucao_valvula", pk=item.pk)


class ExecucaoValvulaRevisarView(LoginRequiredMixin, PermissaoRequeridaMixin, View):
    permission_required = "servicos.revisar_ordem"

    def post(self, request, pk):
        item, invalido = _item_valvula_ou_invalido(pk)
        if invalido is not None:
            messages.error(
                request,
                "A execução de válvula só existe para itens de válvula.",
            )
            return redirect("servicos:detalhe_item_ordem", pk=invalido.pk)
        execucao = item.execucao_valvula_atual
        if execucao is None:
            messages.error(request, "Não há execução para revisar.")
            return redirect("servicos:detalhe_item_ordem", pk=item.pk)
        if _ordem_bloqueada(item) or not execucao.pode_revisar:
            messages.error(request, "Somente execuções aguardando revisão podem ser revisadas.")
            return redirect("servicos:detalhe_execucao_valvula", pk=item.pk)
        form = ExecucaoValvulaForm(
            request.POST,
            instance=execucao,
            somente_revisao=True,
        )
        if not form.is_valid():
            return _render_execucao(request, item, execucao, form)
        erros = execucao.validar_envio_revisao()
        if erros:
            for erro in erros:
                messages.error(request, erro)
            return redirect("servicos:detalhe_execucao_valvula", pk=item.pk)
        with transaction.atomic():
            execucao.observacoes_revisao = form.cleaned_data.get("observacoes_revisao") or ""
            execucao.registrar_revisao(request.user)
            execucao.save(
                update_fields=[
                    "observacoes_revisao",
                    "executor",
                    "executor_nome",
                    "executado_em",
                    "revisor",
                    "revisor_nome",
                    "revisado_em",
                    "atualizado_em",
                ]
            )
            item.sincronizar_com_execucao_valvula(execucao)
        registrar_auditoria(
            request=request,
            acao="EXECUCAO_VALVULA_REVISADA",
            objeto=execucao,
            descricao=(
                f"Execução de {item.codigo_equipamento} revisada "
                f"na {item.ordem_servico.numero}."
            ),
        )
        messages.success(request, "Revisão registrada. A execução pode ser concluída.")
        return redirect("servicos:detalhe_execucao_valvula", pk=item.pk)


class ExecucaoValvulaConcluirView(LoginRequiredMixin, PermissaoRequeridaMixin, View):
    permission_required = "servicos.concluir_ordem"

    def post(self, request, pk):
        item, invalido = _item_valvula_ou_invalido(pk)
        if invalido is not None:
            messages.error(
                request,
                "A execução de válvula só existe para itens de válvula.",
            )
            return redirect("servicos:detalhe_item_ordem", pk=invalido.pk)
        execucao = item.execucao_valvula_atual
        if execucao is None:
            messages.error(request, "Não há execução para concluir.")
            return redirect("servicos:detalhe_item_ordem", pk=item.pk)
        if _ordem_bloqueada(item) or not execucao.pode_concluir:
            messages.error(
                request,
                "Somente execuções revisadas em rascunho podem ser concluídas.",
            )
            return redirect("servicos:detalhe_execucao_valvula", pk=item.pk)
        erros = execucao.validar_conclusao()
        if erros:
            for erro in erros:
                messages.error(request, erro)
            return redirect("servicos:detalhe_execucao_valvula", pk=item.pk)
        with transaction.atomic():
            execucao.status = StatusExecucaoValvula.CONCLUIDA
            execucao.save(update_fields=["status", "atualizado_em"])
            item.sincronizar_com_execucao_valvula(execucao)
        registrar_auditoria(
            request=request,
            acao="EXECUCAO_VALVULA_CONCLUIDA",
            objeto=execucao,
            descricao=(
                f"Execução de {item.codigo_equipamento} concluída "
                f"na {item.ordem_servico.numero}."
            ),
        )
        messages.success(request, "Execução de válvula concluída.")
        return redirect("servicos:detalhe_execucao_valvula", pk=item.pk)


class ExecucaoValvulaCancelarView(LoginRequiredMixin, PermissaoRequeridaMixin, View):
    permission_required = "servicos.change_ordemservico"

    def post(self, request, pk):
        item, invalido = _item_valvula_ou_invalido(pk)
        if invalido is not None:
            messages.error(
                request,
                "A execução de válvula só existe para itens de válvula.",
            )
            return redirect("servicos:detalhe_item_ordem", pk=invalido.pk)
        execucao = item.execucao_valvula_atual
        if execucao is None:
            messages.error(request, "Não há execução para cancelar.")
            return redirect("servicos:detalhe_item_ordem", pk=item.pk)
        if not execucao.pode_cancelar:
            messages.error(request, "Somente rascunhos podem ser cancelados.")
            return redirect("servicos:detalhe_execucao_valvula", pk=item.pk)
        execucao.status = StatusExecucaoValvula.CANCELADA
        execucao.save(update_fields=["status", "atualizado_em"])
        registrar_auditoria(
            request=request,
            acao="EXECUCAO_VALVULA_CANCELADA",
            objeto=execucao,
            descricao=(
                f"Execução de {item.codigo_equipamento} cancelada "
                f"na {item.ordem_servico.numero}."
            ),
        )
        messages.success(request, "Execução de válvula cancelada. O registro foi preservado.")
        return redirect("servicos:detalhe_execucao_valvula", pk=item.pk)

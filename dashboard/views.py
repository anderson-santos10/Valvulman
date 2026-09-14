from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.views.generic import TemplateView

from dashboard.paineis import montar_paineis
from servicos.operacao import indicadores_operacao


class HomeView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        usuario = self.request.user
        context["indicadores"] = indicadores_operacao()
        context["paineis"] = montar_paineis(context["indicadores"])
        context["ver_operacao"] = usuario.has_perm(
            "servicos.view_ordemservico"
        ) or usuario.has_perm("servicos.add_orcamento") or usuario.has_perm(
            "servicos.iniciar_ordem"
        )
        context["ver_comercial"] = usuario.has_perm("servicos.view_orcamento")
        context["ver_financeiro"] = usuario.has_perm("servicos.view_cobranca")
        paineis = context["paineis"]
        paineis["tem_movimento_visivel"] = any(
            (
                context["ver_operacao"] and paineis["operacao"]["tem_dados"],
                usuario.has_perm("servicos.view_calibracao")
                and paineis["calibracoes"]["tem_dados"],
                context["ver_comercial"] and paineis["comercial"]["tem_dados"],
                context["ver_financeiro"] and paineis["financeiro"]["tem_dados"],
            )
        )
        return context


class DesignSystemView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/design_system.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not (
            request.user.is_staff or request.user.is_superuser
        ):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class ConfiguracoesView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/configuracoes.html"

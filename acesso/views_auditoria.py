from datetime import datetime

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.db.models import Q
from django.views.generic import ListView

from acesso.mixins import PermissaoRequeridaMixin
from acesso.models import RegistroAuditoria


class ListaAuditoriaView(LoginRequiredMixin, PermissaoRequeridaMixin, ListView):
    permission_required = "acesso.view_registroauditoria"
    template_name = "acesso/lista_auditoria.html"
    context_object_name = "registros"
    paginate_by = 20

    def get_queryset(self):
        queryset = RegistroAuditoria.objects.select_related("usuario").order_by(
            "-criado_em"
        )
        params = self.request.GET
        usuario_id = (params.get("usuario") or "").strip()
        if usuario_id.isdigit():
            queryset = queryset.filter(usuario_id=int(usuario_id))
        acao = (params.get("acao") or "").strip()
        if acao:
            queryset = queryset.filter(acao=acao)
        modelo = (params.get("modelo") or "").strip()
        if modelo:
            queryset = queryset.filter(modelo=modelo)
        objeto = (params.get("q") or "").strip()
        if objeto:
            queryset = queryset.filter(
                Q(objeto_id__icontains=objeto) | Q(descricao__icontains=objeto)
            )
        data_de = self._parse_data(params.get("data_de"))
        data_ate = self._parse_data(params.get("data_ate"))
        if data_de:
            queryset = queryset.filter(criado_em__date__gte=data_de)
        if data_ate:
            queryset = queryset.filter(criado_em__date__lte=data_ate)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["usuarios"] = User.objects.order_by("username")
        context["acoes"] = (
            RegistroAuditoria.objects.order_by("acao")
            .values_list("acao", flat=True)
            .distinct()
        )
        context["modelos"] = (
            RegistroAuditoria.objects.order_by("modelo")
            .values_list("modelo", flat=True)
            .distinct()
        )
        return context

    def _parse_data(self, valor):
        texto = (valor or "").strip()
        if not texto:
            return None
        try:
            return datetime.strptime(texto, "%Y-%m-%d").date()
        except ValueError:
            return None

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.db.models import Q
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from acesso.auditoria import registrar_auditoria
from acesso.forms import UsuarioForm
from acesso.mixins import PermissaoRequeridaMixin


class UsuariosQuerySetMixin:
    def get_queryset(self):
        return User.objects.prefetch_related("groups").order_by("username")


class ListaUsuariosView(LoginRequiredMixin, PermissaoRequeridaMixin, UsuariosQuerySetMixin, ListView):
    permission_required = "auth.view_user"
    template_name = "acesso/lista_usuarios.html"
    context_object_name = "usuarios"
    paginate_by = 10

    def get_queryset(self):
        queryset = super().get_queryset()
        pesquisa = self.request.GET.get("q", "").strip()
        if pesquisa:
            queryset = queryset.filter(
                Q(username__icontains=pesquisa)
                | Q(first_name__icontains=pesquisa)
                | Q(last_name__icontains=pesquisa)
                | Q(email__icontains=pesquisa)
            )
        return queryset


class UsuarioCreateView(LoginRequiredMixin, PermissaoRequeridaMixin, CreateView):
    permission_required = "auth.add_user"
    model = User
    form_class = UsuarioForm
    template_name = "acesso/cadastro_usuario.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["editor"] = self.request.user
        return kwargs

    def form_valid(self, form):
        self.object = form.save()
        registrar_auditoria(
            request=self.request,
            acao="USUARIO_CRIADO",
            objeto=self.object,
            objeto_id=self.object.username,
            descricao=f"Usuário {self.object.username} criado.",
        )
        messages.success(self.request, "Usuário cadastrado com sucesso!")
        return redirect("acesso:detalhe_usuario", pk=self.object.pk)


class UsuarioDetailView(LoginRequiredMixin, PermissaoRequeridaMixin, UsuariosQuerySetMixin, DetailView):
    permission_required = "auth.view_user"
    model = User
    template_name = "acesso/detalhe_usuario.html"
    context_object_name = "usuario"


class UsuarioUpdateView(LoginRequiredMixin, PermissaoRequeridaMixin, UpdateView):
    permission_required = "auth.change_user"
    model = User
    form_class = UsuarioForm
    template_name = "acesso/editar_usuario.html"
    context_object_name = "usuario"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["editor"] = self.request.user
        return kwargs

    def form_valid(self, form):
        grupos_antes = set(self.object.groups.values_list("name", flat=True))
        self.object = form.save()
        grupos_depois = set(self.object.groups.values_list("name", flat=True))
        descricao = f"Usuário {self.object.username} atualizado."
        acao = "USUARIO_ALTERADO"
        if grupos_antes != grupos_depois:
            acao = "USUARIO_GRUPOS_ALTERADOS"
            descricao = (
                f"Grupos de {self.object.username}: "
                f"{', '.join(sorted(grupos_antes)) or 'nenhum'} → "
                f"{', '.join(sorted(grupos_depois)) or 'nenhum'}."
            )
        registrar_auditoria(
            request=self.request,
            acao=acao,
            objeto=self.object,
            objeto_id=self.object.username,
            descricao=descricao,
        )
        messages.success(self.request, "Usuário atualizado com sucesso!")
        return redirect("acesso:detalhe_usuario", pk=self.object.pk)


class UsuarioAtivarView(LoginRequiredMixin, PermissaoRequeridaMixin, View):
    permission_required = "auth.change_user"

    def get(self, request, pk):
        return HttpResponseNotAllowed(["POST"])

    def post(self, request, pk):
        usuario = get_object_or_404(User, pk=pk)
        usuario.is_active = True
        usuario.save(update_fields=["is_active"])
        registrar_auditoria(
            request=request,
            acao="USUARIO_ATIVADO",
            objeto=usuario,
            objeto_id=usuario.username,
            descricao=f"Usuário {usuario.username} ativado.",
        )
        messages.success(request, f"Usuário {usuario.username} ativado.")
        return redirect("acesso:detalhe_usuario", pk=usuario.pk)


class UsuarioInativarView(LoginRequiredMixin, PermissaoRequeridaMixin, View):
    permission_required = "auth.change_user"

    def get(self, request, pk):
        return HttpResponseNotAllowed(["POST"])

    def post(self, request, pk):
        usuario = get_object_or_404(User, pk=pk)
        if usuario.pk == request.user.pk:
            messages.error(request, "Você não pode inativar o próprio usuário.")
            return redirect("acesso:detalhe_usuario", pk=usuario.pk)
        usuario.is_active = False
        usuario.save(update_fields=["is_active"])
        registrar_auditoria(
            request=request,
            acao="USUARIO_INATIVADO",
            objeto=usuario,
            objeto_id=usuario.username,
            descricao=f"Usuário {usuario.username} inativado.",
        )
        messages.success(request, f"Usuário {usuario.username} inativado.")
        return redirect("acesso:detalhe_usuario", pk=usuario.pk)

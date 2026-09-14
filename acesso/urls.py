from django.urls import path

from .views import (
    ListaUsuariosView,
    UsuarioAtivarView,
    UsuarioCreateView,
    UsuarioDetailView,
    UsuarioInativarView,
    UsuarioUpdateView,
)
from .views_auditoria import ListaAuditoriaView

app_name = "acesso"

urlpatterns = [
    path("usuarios/", ListaUsuariosView.as_view(), name="lista_usuarios"),
    path("usuarios/novo/", UsuarioCreateView.as_view(), name="cadastrar_usuario"),
    path("usuarios/<int:pk>/", UsuarioDetailView.as_view(), name="detalhe_usuario"),
    path(
        "usuarios/<int:pk>/editar/",
        UsuarioUpdateView.as_view(),
        name="editar_usuario",
    ),
    path(
        "usuarios/<int:pk>/ativar/",
        UsuarioAtivarView.as_view(),
        name="ativar_usuario",
    ),
    path(
        "usuarios/<int:pk>/inativar/",
        UsuarioInativarView.as_view(),
        name="inativar_usuario",
    ),
    path("auditoria/", ListaAuditoriaView.as_view(), name="lista_auditoria"),
]

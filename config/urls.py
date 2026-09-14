from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from dashboard.views import ConfiguracoesView, DesignSystemView, HomeView
from servicos.views import ValidarCertificadoPublicoView

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path(
        "logout/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),
    path(
        "validar/<str:token>/",
        ValidarCertificadoPublicoView.as_view(),
        name="validar_certificado",
    ),
    # Dashboard / Home
    path(
        "",
        HomeView.as_view(),
        name="home",
    ),
    path(
        "design-system/",
        DesignSystemView.as_view(),
        name="design_system",
    ),
    path(
        "configuracoes/",
        ConfiguracoesView.as_view(),
        name="configuracoes",
    ),
    # Serviços
    path(
        "servicos/",
        include("servicos.urls"),
    ),
    # Clientes
    path("clientes/", include("clientes.urls"),),
    path("", include("acesso.urls")),
]
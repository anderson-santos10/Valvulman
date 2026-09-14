from django.urls import path

from .views import (
    ClienteCreateView,
    ClienteDetailView,
    ClienteUpdateView,
    ListaClientesView,
)

app_name = "clientes"

urlpatterns = [
    path("novo/", ClienteCreateView.as_view(), name="cadastrar_cliente"),
    path("editar/<int:pk>/", ClienteUpdateView.as_view(), name="editar_cliente"),
    path("<int:pk>/", ClienteDetailView.as_view(), name="detalhe_cliente"),
    path("", ListaClientesView.as_view(), name="lista_clientes"),
]

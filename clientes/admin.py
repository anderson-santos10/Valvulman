from django.contrib import admin

from .forms import ClienteForm
from .models import Cliente


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    form = ClienteForm
    list_display = ("nome", "cnpj", "telefone", "email", "cep", "endereco", "criado_em")
    search_fields = ("nome", "cnpj", "endereco", "cep", "contato_principal", "telefone", "email")
    list_filter = ("criado_em",)
    ordering = ("nome",)

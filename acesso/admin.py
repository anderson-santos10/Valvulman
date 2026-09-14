from django.contrib import admin

from .models import RegistroAuditoria


@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    list_display = (
        "criado_em",
        "usuario",
        "acao",
        "modelo",
        "objeto_id",
        "ip",
    )
    list_filter = ("acao", "modelo", "criado_em")
    search_fields = ("acao", "modelo", "objeto_id", "descricao", "usuario__username")
    ordering = ("-criado_em",)
    date_hierarchy = "criado_em"
    readonly_fields = (
        "usuario",
        "acao",
        "modelo",
        "objeto_id",
        "descricao",
        "ip",
        "criado_em",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

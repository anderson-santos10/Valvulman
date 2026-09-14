from django.conf import settings
from django.db import models


class RegistroAuditoria(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="registros_auditoria",
    )
    acao = models.CharField(max_length=100)
    modelo = models.CharField(max_length=100)
    objeto_id = models.CharField(max_length=100, blank=True)
    descricao = models.TextField(blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Registro de auditoria"
        verbose_name_plural = "Registros de auditoria"
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["acao"]),
            models.Index(fields=["modelo"]),
            models.Index(fields=["criado_em"]),
        ]

    def __str__(self):
        return f"{self.acao} — {self.modelo} {self.objeto_id}"

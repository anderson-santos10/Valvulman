from django.db import models


class Cliente(models.Model):
    nome = models.CharField(max_length=150)
    cnpj = models.CharField(max_length=18, unique=True)
    cep = models.CharField(max_length=9)
    endereco = models.CharField(max_length=255)
    contato_principal = models.CharField(max_length=150, blank=True)
    telefone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nome

    def dados_contato(self):
        return {
            "contato_principal": self.contato_principal or "",
            "telefone": self.telefone or "",
            "email": self.email or "",
        }
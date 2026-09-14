from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

from acesso.permissoes import (
    APPS_ADMINISTRADOR,
    GRUPO_ADMINISTRADOR,
    GRUPOS,
    PERMISSOES_GRUPOS,
)


class Command(BaseCommand):
    help = "Cria ou atualiza grupos de acesso e suas permissões."

    def handle(self, *args, **options):
        criados = []
        atualizados = []
        for nome in GRUPOS:
            grupo, novo = Group.objects.get_or_create(name=nome)
            if novo:
                criados.append(nome)
            else:
                atualizados.append(nome)
            if nome == GRUPO_ADMINISTRADOR:
                perms = Permission.objects.filter(
                    content_type__app_label__in=APPS_ADMINISTRADOR
                )
            else:
                perms = self._buscar(PERMISSOES_GRUPOS[nome])
            grupo.permissions.set(perms)
        self.stdout.write(
            self.style.SUCCESS(
                "Grupos criados: {0}. Atualizados: {1}.".format(
                    ", ".join(criados) or "nenhum",
                    ", ".join(atualizados) or "nenhum",
                )
            )
        )

    def _buscar(self, codigos):
        encontrados = []
        for codigo in codigos:
            app, codename = codigo.split(".", 1)
            try:
                encontrados.append(
                    Permission.objects.get(
                        content_type__app_label=app,
                        codename=codename,
                    )
                )
            except Permission.DoesNotExist:
                self.stderr.write(self.style.WARNING(f"Permissão ausente: {codigo}"))
        return encontrados

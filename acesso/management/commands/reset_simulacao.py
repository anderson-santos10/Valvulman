from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand, CommandError

from acesso.reset_simulacao import (
    CONFIRMACAO_RESET,
    MODELOS_NEGOCIO,
    MODELOS_PRESERVADOS,
    apagar_dados_negocio,
    fotografia_acesso,
    fotografia_negocio,
)


class Command(BaseCommand):
    help = (
        "Apaga dados de negócio para uma nova simulação. "
        "Preserva usuários, grupos, permissões e o schema. Somente desenvolvimento."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirmar",
            default="",
            help=f'Deve ser exatamente "{CONFIRMACAO_RESET}" para executar sem prompt.',
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "reset_simulacao é bloqueado quando DEBUG=False (produção)."
            )

        self._imprimir_aviso()
        acesso_antes = fotografia_acesso()
        negocio_antes = fotografia_negocio()
        self._imprimir_fotografia("DADOS ATUAIS", negocio_antes, acesso_antes)

        if not self._confirmado(options.get("confirmar") or ""):
            raise CommandError("Reset cancelado. Nenhuma alteração foi feita.")

        total, _detalhes = apagar_dados_negocio()
        acesso_depois = fotografia_acesso()
        negocio_depois = fotografia_negocio()

        if acesso_depois["usuarios"] != acesso_antes["usuarios"]:
            raise CommandError("Abortado: a quantidade de usuários mudou durante o reset.")
        if acesso_depois["grupos"] != acesso_antes["grupos"]:
            raise CommandError("Abortado: a quantidade de grupos mudou durante o reset.")
        if acesso_depois["permissoes"] != acesso_antes["permissoes"]:
            raise CommandError(
                "Abortado: a quantidade de permissões mudou durante o reset."
            )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("RESET CONCLUÍDO"))
        self.stdout.write(f"Dados de negócio removidos: {total} registros")
        self.stdout.write("")
        self.stdout.write("Preservados:")
        self.stdout.write(f"Usuários: {acesso_depois['usuarios']}")
        self.stdout.write(f"Grupos: {acesso_depois['grupos']}")
        self.stdout.write(f"Permissões: {acesso_depois['permissoes']}")
        self.stdout.write(f"Sessões (mantidas): {Session.objects.count()}")
        self.stdout.write("")
        self._imprimir_fotografia("DEPOIS", negocio_depois, acesso_depois)

    def _confirmado(self, token):
        if token == CONFIRMACAO_RESET:
            return True
        self.stdout.write("")
        self.stdout.write("Deseja continuar?")
        self.stdout.write("")
        self.stdout.write("Digite:")
        self.stdout.write(CONFIRMACAO_RESET)
        try:
            resposta = input("> ").strip()
        except EOFError as exc:
            raise CommandError(
                'Confirmação ausente. Use --confirmar RESETAR em ambiente não interativo.'
            ) from exc
        return resposta == CONFIRMACAO_RESET

    def _imprimir_aviso(self):
        self.stdout.write("")
        self.stdout.write(self.style.WARNING("ATENÇÃO"))
        self.stdout.write("")
        self.stdout.write("Este comando apagará todos os dados de negócio do Valvulman.")
        self.stdout.write("")
        self.stdout.write("Serão preservados:")
        for modelo in MODELOS_PRESERVADOS:
            self.stdout.write(f"- {modelo._meta.label}")
        self.stdout.write("- sessões (django.contrib.sessions)")
        self.stdout.write("- estrutura do banco / migrations")
        self.stdout.write("")
        self.stdout.write("Serão apagados:")
        for modelo in MODELOS_NEGOCIO:
            self.stdout.write(f"- {modelo._meta.label}")

    def _imprimir_fotografia(self, titulo, negocio, acesso):
        self.stdout.write("")
        self.stdout.write(titulo)
        self.stdout.write("")
        for rotulo, quantidade in negocio:
            self.stdout.write(f"{rotulo}: {quantidade}")
        self.stdout.write(f"Usuários: {acesso['usuarios']}")
        self.stdout.write(f"Grupos: {acesso['grupos']}")
        self.stdout.write(f"Permissões: {acesso['permissoes']}")

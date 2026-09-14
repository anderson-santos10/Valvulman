from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from servicos.demo_metrologia import (
    OBSERVACAO_DEMO,
    PADRAO_DEMO_CODIGO,
    PADRAO_DEMO_NOME,
    PROCEDIMENTO_DEMO_CODIGO,
    PROCEDIMENTO_DEMO_NOME,
    CRITERIO_DEMO,
)
from servicos.models import PadraoMedicao, UnidadePressao


class Command(BaseCommand):
    help = (
        "Cria o padrão DEMO para simulação de calibração (somente desenvolvimento). "
        "Não afirma rastreabilidade nem certificado real."
    )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "seed_metrologia_demo só pode ser usado com DEBUG=True."
            )
        padrao, criado = PadraoMedicao.objects.update_or_create(
            codigo=PADRAO_DEMO_CODIGO,
            defaults={
                "identificacao": PADRAO_DEMO_NOME,
                "tipo": "Pressão — DEMO",
                "unidade": UnidadePressao.BAR,
                "faixa_minima": 0,
                "faixa_maxima": 16,
                "ativo": True,
                "numero_certificado": "",
                "data_calibracao": None,
                "data_validade": None,
                "observacoes": OBSERVACAO_DEMO,
            },
        )
        acao = "criado" if criado else "atualizado"
        self.stdout.write(self.style.SUCCESS(f"Padrão {padrao.codigo} {acao}."))
        self.stdout.write("")
        self.stdout.write("Use na tela de calibração (texto livre / seleção):")
        self.stdout.write(f"  Procedimento: {PROCEDIMENTO_DEMO_CODIGO}")
        self.stdout.write(f"  ({PROCEDIMENTO_DEMO_NOME})")
        self.stdout.write(f"  Critério: {CRITERIO_DEMO}")
        self.stdout.write("  Tolerância: valor absoluto na unidade do instrumento (ex.: 0.1)")
        self.stdout.write("")
        self.stdout.write(
            "Estes dados servem apenas para validar o software. "
            "Não são rastreáveis e não afirmam ISO 17025, RBC ou INMETRO."
        )

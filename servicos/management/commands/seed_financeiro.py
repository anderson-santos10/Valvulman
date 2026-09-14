from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from clientes.models import Cliente
from servicos.models import Cobranca, FormaPagamento


SEED_CLIENTE = "Cliente Financeiro Seed"
SEED_CNPJ = "04.252.011/0001-10"
MARCAS = {
    "pendente": "[SEED] Cobrança pendente",
    "parcial": "[SEED] Cobrança parcial",
    "vencida": "[SEED] Cobrança vencida",
    "paga": "[SEED] Cobrança paga",
}


class Command(BaseCommand):
    help = "Cria massa fictícia de contas a receber (somente desenvolvimento)."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("O comando seed_financeiro só pode ser usado em desenvolvimento.")
        hoje = timezone.localdate()
        cliente, _ = Cliente.objects.get_or_create(
            nome=SEED_CLIENTE,
            defaults={
                "cnpj": SEED_CNPJ,
                "cep": "17512-400",
                "endereco": "Rua Financeira, 13",
            },
        )
        criadas = 0
        cob1 = self._cobranca(
            cliente,
            MARCAS["pendente"],
            Decimal("500.00"),
            hoje + timedelta(days=15),
        )
        if cob1:
            criadas += 1
        cob2 = self._cobranca(
            cliente,
            MARCAS["parcial"],
            Decimal("1000.00"),
            hoje + timedelta(days=10),
        )
        if cob2:
            criadas += 1
            self._pagamento(cob2, Decimal("400.00"), hoje)
        cob3 = self._cobranca(
            cliente,
            MARCAS["vencida"],
            Decimal("750.00"),
            hoje - timedelta(days=5),
        )
        if cob3:
            criadas += 1
        cob4 = self._cobranca(
            cliente,
            MARCAS["paga"],
            Decimal("300.00"),
            hoje + timedelta(days=20),
        )
        if cob4:
            criadas += 1
            self._pagamento(cob4, Decimal("300.00"), hoje)
        self.stdout.write(
            self.style.SUCCESS(
                f"Seed financeiro concluído. Cliente: {cliente.nome}. Novas cobranças: {criadas}."
            )
        )

    def _cobranca(self, cliente, descricao, valor, vencimento):
        existente = Cobranca.objects.filter(descricao=descricao).first()
        if existente:
            return None
        return Cobranca.criar(
            cliente=cliente,
            descricao=descricao,
            valor_original=valor,
            desconto=Decimal("0.00"),
            acrescimo=Decimal("0.00"),
            data_emissao=timezone.localdate(),
            data_vencimento=vencimento,
            forma_pagamento=FormaPagamento.PIX,
            observacoes="Massa fictícia. Sem boleto ou PIX real.",
        )

    def _pagamento(self, cobranca, valor, data):
        if cobranca.pagamentos.exists():
            return
        cobranca.registrar_pagamento(
            data_pagamento=data,
            valor=valor,
            forma_pagamento=FormaPagamento.PIX,
            observacoes="Pagamento de seed.",
        )

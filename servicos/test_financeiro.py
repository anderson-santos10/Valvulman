from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from clientes.models import Cliente

from .models import (
    Cobranca,
    FormaPagamento,
    Instrumento,
    ItemOrcamento,
    ItemOrdemServico,
    Orcamento,
    OrdemServico,
    Pagamento,
    ServicoSolicitado,
    StatusCobranca,
    StatusItemOrdem,
    StatusOrcamento,
    StatusOrdemServico,
    TipoInstrumento,
    UnidadePressao,
)
from .operacao import indicadores_operacao


class FinanceiroTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="operador",
            email="operador@example.com",
            password="senha-segura-123",
        )
        self.client.login(username="operador", password="senha-segura-123")
        self.hoje = timezone.localdate()
        self.cliente_a = Cliente.objects.create(
            nome="Empresa ABC",
            cnpj="11.222.333/0001-81",
            cep="17512-400",
            endereco="Rua Industrial, 10",
        )
        self.cliente_b = Cliente.objects.create(
            nome="Empresa XYZ",
            cnpj="11.444.777/0001-61",
            cep="17512-400",
            endereco="Rua Comercial, 20",
        )
        self.instrumento = Instrumento.objects.create(
            cliente=self.cliente_a,
            codigo="MAN-001",
            tag="PI-01",
            numero_serie="SN-001",
            tipo=TipoInstrumento.MANOMETRO,
            faixa_minima=Decimal("0"),
            faixa_maxima=Decimal("10"),
            unidade=UnidadePressao.BAR,
        )

    def _cobranca(self, cliente=None, **extra):
        dados = {
            "cliente": cliente or self.cliente_a,
            "descricao": extra.pop("descricao", "Serviço técnico"),
            "valor_original": extra.pop("valor_original", Decimal("500.00")),
            "desconto": extra.pop("desconto", Decimal("0.00")),
            "acrescimo": extra.pop("acrescimo", Decimal("0.00")),
            "data_emissao": extra.pop("data_emissao", self.hoje),
            "data_vencimento": extra.pop(
                "data_vencimento", self.hoje + timedelta(days=10)
            ),
        }
        dados.update(extra)
        return Cobranca.criar(**dados)

    def _item_orcamento(self, orcamento, **extra):
        dados = {
            "orcamento": orcamento,
            "servico": extra.pop("servico", ServicoSolicitado.AJUSTE),
            "instrumento": extra.pop("instrumento", self.instrumento),
            "descricao": extra.pop("descricao", "Ajuste de manômetro."),
            "quantidade": extra.pop("quantidade", 1),
            "valor_unitario": extra.pop("valor_unitario", Decimal("200.00")),
            "desconto": extra.pop("desconto", Decimal("0.00")),
            "ordem": extra.pop("ordem", 1),
        }
        dados.update(extra)
        item = ItemOrcamento(**dados)
        item.full_clean()
        item.save()
        return item

    def test_numero_automatico_e_unico(self):
        primeira = self._cobranca()
        segunda = self._cobranca(descricao="Outra cobrança")
        self.assertEqual(primeira.numero, "COB-000001")
        self.assertEqual(segunda.numero, "COB-000002")
        self.assertEqual(Cobranca.objects.filter(numero="COB-000001").count(), 1)

    def test_cliente_obrigatorio_e_valores(self):
        with self.assertRaises(ValidationError):
            cobranca = Cobranca(
                descricao="Sem cliente",
                valor_original=Decimal("10.00"),
                data_emissao=self.hoje,
                data_vencimento=self.hoje,
            )
            cobranca.full_clean()
        cobranca = self._cobranca(
            valor_original=Decimal("100.00"),
            desconto=Decimal("10.00"),
            acrescimo=Decimal("5.00"),
        )
        self.assertEqual(cobranca.valor_final, Decimal("95.00"))
        with self.assertRaises(ValidationError):
            self._cobranca(valor_original=Decimal("10.00"), desconto=Decimal("20.00"))

    def test_status_pendente_parcial_pago_vencido_sem_job(self):
        pendente = self._cobranca()
        self.assertEqual(pendente.situacao_codigo, StatusCobranca.PENDENTE)
        parcial = self._cobranca(descricao="Parcial", valor_original=Decimal("1000.00"))
        parcial.registrar_pagamento(
            data_pagamento=self.hoje,
            valor=Decimal("400.00"),
            forma_pagamento=FormaPagamento.PIX,
        )
        parcial.refresh_from_db()
        self.assertEqual(parcial.status, StatusCobranca.PARCIAL)
        self.assertEqual(parcial.saldo_devedor(), Decimal("600.00"))
        restante = parcial.registrar_pagamento(
            data_pagamento=self.hoje,
            valor=Decimal("600.00"),
            forma_pagamento=FormaPagamento.DINHEIRO,
        )
        self.assertEqual(restante.valor, Decimal("600.00"))
        parcial.refresh_from_db()
        self.assertEqual(parcial.status, StatusCobranca.PAGO)
        self.assertEqual(parcial.saldo_devedor(), Decimal("0.00"))
        vencida = self._cobranca(
            descricao="Vencida",
            data_vencimento=self.hoje - timedelta(days=1),
        )
        self.assertEqual(vencida.status, StatusCobranca.PENDENTE)
        self.assertEqual(vencida.situacao_codigo, StatusCobranca.VENCIDO)

    def test_pagamento_excedente_e_cancelada(self):
        cobranca = self._cobranca(valor_original=Decimal("100.00"))
        with self.assertRaises(ValidationError):
            cobranca.registrar_pagamento(
                data_pagamento=self.hoje,
                valor=Decimal("150.00"),
                forma_pagamento=FormaPagamento.PIX,
            )
        cobranca.cancelar()
        with self.assertRaises(ValidationError):
            cobranca.registrar_pagamento(
                data_pagamento=self.hoje,
                valor=Decimal("10.00"),
                forma_pagamento=FormaPagamento.PIX,
            )
        pago = self._cobranca(descricao="Paga", valor_original=Decimal("50.00"))
        pago.registrar_pagamento(
            data_pagamento=self.hoje,
            valor=Decimal("50.00"),
            forma_pagamento=FormaPagamento.BOLETO,
        )
        self.assertFalse(pago.cancelar()[0])

    def test_nao_exclui_fisicamente(self):
        cobranca = self._cobranca()
        with self.assertRaises(ValidationError):
            cobranca.delete()
        pagamento = cobranca.registrar_pagamento(
            data_pagamento=self.hoje,
            valor=Decimal("10.00"),
            forma_pagamento=FormaPagamento.OUTRO,
        )
        with self.assertRaises(ValidationError):
            pagamento.delete()
        self.assertTrue(Cobranca.objects.filter(pk=cobranca.pk).exists())
        self.assertTrue(Pagamento.objects.filter(pk=pagamento.pk).exists())

    def test_orcamento_e_os_do_mesmo_cliente(self):
        orcamento_a = Orcamento.criar(cliente=self.cliente_a, data_emissao=self.hoje)
        orcamento_b = Orcamento.criar(cliente=self.cliente_b, data_emissao=self.hoje)
        ordem_b = OrdemServico.criar(cliente=self.cliente_b, data_entrada=self.hoje)
        with self.assertRaises(ValidationError):
            self._cobranca(orcamento=orcamento_b)
        with self.assertRaises(ValidationError):
            self._cobranca(ordem_servico=ordem_b)
        ordem_a = OrdemServico.criar(
            cliente=self.cliente_a,
            data_entrada=self.hoje,
            orcamento=orcamento_a,
        )
        cobranca = self._cobranca(orcamento=orcamento_a, ordem_servico=ordem_a)
        self.assertEqual(cobranca.cliente_id, self.cliente_a.pk)
        ordem_sem_orcamento = OrdemServico.criar(
            cliente=self.cliente_a,
            data_entrada=self.hoje,
        )
        self._cobranca(
            descricao="OS manual",
            ordem_servico=ordem_sem_orcamento,
        )
        orcamento_extra = Orcamento.criar(cliente=self.cliente_a, data_emissao=self.hoje)
        ordem_outro = OrdemServico.criar(
            cliente=self.cliente_a,
            data_entrada=self.hoje,
            orcamento=orcamento_extra,
        )
        with self.assertRaises(ValidationError):
            self._cobranca(
                descricao="Mistura",
                orcamento=orcamento_a,
                ordem_servico=ordem_outro,
            )

    def test_login_csrf_e_get_nao_altera(self):
        cobranca = self._cobranca()
        self.client.logout()
        lista = self.client.get(reverse("servicos:lista_cobrancas"))
        self.assertEqual(lista.status_code, 302)
        self.assertIn(reverse("login"), lista.url)
        self.client.login(username="operador", password="senha-segura-123")
        get_pagar = self.client.get(
            reverse("servicos:registrar_pagamento", args=[cobranca.pk])
        )
        self.assertEqual(get_pagar.status_code, 405)
        get_cancelar = self.client.get(
            reverse("servicos:cancelar_cobranca", args=[cobranca.pk])
        )
        self.assertEqual(get_cancelar.status_code, 405)
        cobranca.refresh_from_db()
        self.assertEqual(cobranca.status, StatusCobranca.PENDENTE)
        csrf = Client(enforce_csrf_checks=True)
        csrf.login(username="operador", password="senha-segura-123")
        self.assertEqual(
            csrf.post(reverse("servicos:cancelar_cobranca", args=[cobranca.pk])).status_code,
            403,
        )
        self.client.post(reverse("servicos:cancelar_cobranca", args=[cobranca.pk]))
        cobranca.refresh_from_db()
        self.assertEqual(cobranca.status, StatusCobranca.CANCELADO)

    def test_gerar_cobranca_da_os_sem_duplicar(self):
        ordem = OrdemServico.criar(
            cliente=self.cliente_a,
            data_entrada=self.hoje,
            status=StatusOrdemServico.CONCLUIDA,
        )
        ItemOrdemServico.objects.create(
            ordem_servico=ordem,
            instrumento=self.instrumento,
            servico_solicitado=ServicoSolicitado.AJUSTE,
        )
        gerar = self.client.post(
            reverse("servicos:gerar_cobranca_ordem", args=[ordem.pk]),
            {
                "cliente": self.cliente_a.pk,
                "descricao": f"Serviços da {ordem.numero}",
                "valor_original": "250.00",
                "desconto": "0.00",
                "acrescimo": "0.00",
                "data_emissao": self.hoje.isoformat(),
                "data_vencimento": self.hoje.isoformat(),
            },
        )
        cobranca = Cobranca.objects.get()
        self.assertRedirects(
            gerar, reverse("servicos:detalhe_cobranca", args=[cobranca.pk])
        )
        self.assertEqual(cobranca.ordem_servico_id, ordem.pk)
        segunda = self.client.post(
            reverse("servicos:gerar_cobranca_ordem", args=[ordem.pk]),
            {
                "cliente": self.cliente_a.pk,
                "descricao": "Tentativa duplicada",
                "valor_original": "250.00",
                "desconto": "0.00",
                "acrescimo": "0.00",
                "data_emissao": self.hoje.isoformat(),
                "data_vencimento": self.hoje.isoformat(),
            },
        )
        self.assertEqual(Cobranca.objects.count(), 1)
        self.assertRedirects(
            segunda, reverse("servicos:detalhe_cobranca", args=[cobranca.pk])
        )
        aberta = OrdemServico.criar(cliente=self.cliente_a, data_entrada=self.hoje)
        recusa = self.client.get(
            reverse("servicos:gerar_cobranca_ordem", args=[aberta.pk])
        )
        self.assertRedirects(recusa, reverse("servicos:detalhe_ordem", args=[aberta.pk]))

    def test_impressao_login_404_e_conteudo(self):
        cobranca = self._cobranca(descricao="Calibração comercial")
        cobranca.registrar_pagamento(
            data_pagamento=self.hoje,
            valor=Decimal("100.00"),
            forma_pagamento=FormaPagamento.TRANSFERENCIA,
        )
        pagina = self.client.get(
            reverse("servicos:imprimir_cobranca", args=[cobranca.pk])
        )
        self.assertContains(pagina, "COB-000001")
        self.assertContains(pagina, "Empresa ABC")
        self.assertContains(pagina, "Calibração comercial")
        self.assertContains(pagina, "500")
        self.assertContains(pagina, "100")
        self.assertContains(pagina, "COBRANÇA")
        self.assertNotContains(pagina, "linha digitável")
        self.assertEqual(
            self.client.get(reverse("servicos:imprimir_cobranca", args=[99999])).status_code,
            404,
        )
        self.client.logout()
        self.assertEqual(
            self.client.get(
                reverse("servicos:imprimir_cobranca", args=[cobranca.pk])
            ).status_code,
            302,
        )

    def test_lista_filtros_e_pagamento_http(self):
        futura = self._cobranca()
        vencida = self._cobranca(
            descricao="Vencida lista",
            data_vencimento=self.hoje - timedelta(days=2),
        )
        lista = self.client.get(reverse("servicos:lista_cobrancas"), {"vencidas": "1"})
        self.assertContains(lista, vencida.numero)
        self.assertNotContains(lista, futura.numero)
        pagar = self.client.post(
            reverse("servicos:registrar_pagamento", args=[futura.pk]),
            {
                "data_pagamento": self.hoje.isoformat(),
                "valor": "200.00",
                "forma_pagamento": FormaPagamento.CARTAO,
            },
        )
        self.assertRedirects(
            pagar, reverse("servicos:detalhe_cobranca", args=[futura.pk])
        )
        futura.refresh_from_db()
        self.assertEqual(futura.status, StatusCobranca.PARCIAL)
        detalhe_cliente = self.client.get(
            reverse("clientes:detalhe_cliente", args=[self.cliente_a.pk])
        )
        self.assertContains(detalhe_cliente, "Total em aberto")
        self.assertContains(detalhe_cliente, futura.numero)

    def test_fluxo_completo_orcamento_os_cobranca_pagamento(self):
        orcamento = Orcamento.criar(cliente=self.cliente_a, data_emissao=self.hoje)
        self._item_orcamento(orcamento, valor_unitario=Decimal("200.00"))
        self.assertTrue(orcamento.alterar_status(StatusOrcamento.ENVIADO)[0])
        self.assertTrue(orcamento.alterar_status(StatusOrcamento.APROVADO)[0])
        ordem, erro = orcamento.gerar_ordem_servico()
        self.assertFalse(erro)
        self.assertIsNotNone(ordem)
        self.assertEqual(ordem.status, StatusOrdemServico.RECEBIDA)
        item_os = ordem.itens.get()
        item_os.servico_solicitado = ServicoSolicitado.AJUSTE
        item_os.status = StatusItemOrdem.CONCLUIDO
        item_os.save(update_fields=["servico_solicitado", "status"])
        self.assertTrue(ordem.alterar_status(StatusOrdemServico.EM_EXECUCAO)[0])
        self.assertTrue(ordem.alterar_status(StatusOrdemServico.CONCLUIDA)[0])
        gerar = self.client.post(
            reverse("servicos:gerar_cobranca_ordem", args=[ordem.pk]),
            {
                "cliente": self.cliente_a.pk,
                "orcamento": orcamento.pk,
                "ordem_servico": ordem.pk,
                "descricao": f"Serviços da {ordem.numero}",
                "valor_original": "200.00",
                "desconto": "0.00",
                "acrescimo": "0.00",
                "data_emissao": self.hoje.isoformat(),
                "data_vencimento": self.hoje.isoformat(),
            },
        )
        cobranca = Cobranca.objects.get(ordem_servico=ordem)
        self.assertRedirects(
            gerar, reverse("servicos:detalhe_cobranca", args=[cobranca.pk])
        )
        cobranca.registrar_pagamento(
            data_pagamento=self.hoje,
            valor=Decimal("80.00"),
            forma_pagamento=FormaPagamento.PIX,
        )
        cobranca.refresh_from_db()
        self.assertEqual(cobranca.situacao_codigo, StatusCobranca.PARCIAL)
        cobranca.registrar_pagamento(
            data_pagamento=self.hoje,
            valor=Decimal("120.00"),
            forma_pagamento=FormaPagamento.PIX,
        )
        cobranca.refresh_from_db()
        orcamento.refresh_from_db()
        ordem.refresh_from_db()
        self.assertEqual(orcamento.status, StatusOrcamento.APROVADO)
        self.assertEqual(ordem.status, StatusOrdemServico.CONCLUIDA)
        self.assertEqual(cobranca.status, StatusCobranca.PAGO)
        self.assertEqual(cobranca.saldo_devedor(), Decimal("0.00"))
        indicadores = indicadores_operacao(hoje=self.hoje)
        self.assertEqual(indicadores["recebido_mes"], Decimal("200.00"))
        home = self.client.get(reverse("home"))
        self.assertContains(home, "Contas a receber")
        self.assertContains(home, "Recebido no mês")

    @override_settings(DEBUG=True)
    def test_seed_financeiro_idempotente(self):
        call_command("seed_financeiro")
        call_command("seed_financeiro")
        self.assertEqual(
            Cobranca.objects.filter(descricao__startswith="[SEED]").count(), 4
        )
        vencida = Cobranca.objects.get(descricao="[SEED] Cobrança vencida")
        self.assertEqual(vencida.situacao_codigo, StatusCobranca.VENCIDO)
        paga = Cobranca.objects.get(descricao="[SEED] Cobrança paga")
        self.assertEqual(paga.status, StatusCobranca.PAGO)
        parcial = Cobranca.objects.get(descricao="[SEED] Cobrança parcial")
        self.assertEqual(parcial.saldo_devedor(), Decimal("600.00"))

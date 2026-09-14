from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from clientes.models import Cliente

from .models import (
    Calibracao,
    Instrumento,
    ItemOrdemServico,
    OrdemServico,
    ServicoSolicitado,
    StatusCalibracao,
    StatusItemOrdem,
    StatusOrdemServico,
    TipoEquipamento,
    TipoInstrumento,
    UnidadePressao,
    Valvula,
)


class OrdemServicoUnificadaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="operador",
            email="operador@example.com",
            password="senha-segura-123",
        )
        self.client.login(username="operador", password="senha-segura-123")
        self.cliente = Cliente.objects.create(
            nome="Metalúrgica Alfa Ltda.",
            cnpj="11.222.333/0001-81",
            cep="17512-400",
            endereco="Rua Industrial, 10",
        )
        self.man_001 = Instrumento.objects.create(
            cliente=self.cliente,
            codigo="MAN-001",
            fabricante="Wika",
            modelo="232.50",
            faixa_minima=Decimal("0"),
            faixa_maxima=Decimal("10"),
            unidade=UnidadePressao.BAR,
            tipo=TipoInstrumento.MANOMETRO,
        )
        self.man_002 = Instrumento.objects.create(
            cliente=self.cliente,
            codigo="MAN-002",
            fabricante="Wika",
            faixa_minima=Decimal("0"),
            faixa_maxima=Decimal("16"),
            unidade=UnidadePressao.BAR,
            tipo=TipoInstrumento.MANOMETRO,
        )
        self.val_001 = Valvula.objects.create(
            cliente=self.cliente,
            codigo="VAL-001",
            fabricante="Spirax",
            modelo="SV-100",
            diametro_nominal='2"',
            pressao_ajuste=Decimal("8"),
            unidade_pressao=UnidadePressao.BAR,
        )
        self.val_002 = Valvula.objects.create(
            cliente=self.cliente,
            codigo="VAL-002",
            fabricante="Spirax",
            modelo="SV-200",
            diametro_nominal='2"',
            pressao_ajuste=Decimal("10"),
            unidade_pressao=UnidadePressao.BAR,
        )

    def _os(self, status=StatusOrdemServico.ABERTA):
        return OrdemServico.criar(
            cliente=self.cliente,
            data_entrada=date(2026, 9, 13),
            status=status,
        )

    def _item_man(self, ordem, instrumento, servico=ServicoSolicitado.CALIBRACAO, **extra):
        return ItemOrdemServico.objects.create(
            ordem_servico=ordem,
            tipo_equipamento=TipoEquipamento.INSTRUMENTO,
            instrumento=instrumento,
            servico_solicitado=servico,
            condicao_recebimento=extra.pop("condicao", "Bom estado"),
            **extra,
        )

    def _item_val(self, ordem, valvula, servico=ServicoSolicitado.MANUTENCAO, **extra):
        return ItemOrdemServico.objects.create(
            ordem_servico=ordem,
            tipo_equipamento=TipoEquipamento.VALVULA,
            valvula=valvula,
            servico_solicitado=servico,
            condicao_recebimento=extra.pop("condicao", "Bom estado"),
            **extra,
        )

    def test_os_somente_manometros(self):
        ordem = self._os()
        self._item_man(ordem, self.man_001)
        self._item_man(ordem, self.man_002)
        self.assertTrue(ordem.alterar_status(StatusOrdemServico.RECEBIDA)[0])
        progresso = ordem.resumo_progresso()
        self.assertEqual(progresso["manometros"], 2)
        self.assertEqual(progresso["valvulas"], 0)
        self.assertEqual(progresso["servicos"][ServicoSolicitado.CALIBRACAO], 2)

    def test_os_somente_valvulas(self):
        ordem = self._os()
        self._item_val(ordem, self.val_001)
        self._item_val(ordem, self.val_002)
        self.assertTrue(ordem.alterar_status(StatusOrdemServico.RECEBIDA)[0])
        progresso = ordem.resumo_progresso()
        self.assertEqual(progresso["manometros"], 0)
        self.assertEqual(progresso["valvulas"], 2)
        self.assertEqual(progresso["servicos"][ServicoSolicitado.MANUTENCAO], 2)

    def test_cenario_aceitacao_os_mista_progresso_e_status(self):
        dados = {
            "cliente": self.cliente.pk,
            "data_entrada": "2026-09-13",
            "solicitante": "Recepção",
            "itens-TOTAL_FORMS": "3",
            "itens-INITIAL_FORMS": "0",
            "itens-MIN_NUM_FORMS": "0",
            "itens-MAX_NUM_FORMS": "1000",
            "itens-0-tipo_equipamento": TipoEquipamento.INSTRUMENTO,
            "itens-0-instrumento": str(self.man_001.pk),
            "itens-0-servico_solicitado": ServicoSolicitado.CALIBRACAO,
            "itens-0-condicao_recebimento": "Bom estado",
            "itens-0-observacoes_recebimento": "",
            "itens-0-observacoes": "",
            "itens-1-tipo_equipamento": TipoEquipamento.INSTRUMENTO,
            "itens-1-instrumento": str(self.man_002.pk),
            "itens-1-servico_solicitado": ServicoSolicitado.CALIBRACAO,
            "itens-1-condicao_recebimento": "Bom estado",
            "itens-1-observacoes_recebimento": "",
            "itens-1-observacoes": "",
            "itens-2-tipo_equipamento": TipoEquipamento.VALVULA,
            "itens-2-valvula": str(self.val_001.pk),
            "itens-2-servico_solicitado": ServicoSolicitado.MANUTENCAO,
            "itens-2-condicao_recebimento": "Com corrosão",
            "itens-2-observacoes_recebimento": "Corrosão externa",
            "itens-2-observacoes": "",
        }
        response = self.client.post(reverse("servicos:cadastrar_ordem"), dados)
        ordem = OrdemServico.objects.get()
        self.assertRedirects(response, reverse("servicos:detalhe_ordem", args=[ordem.pk]))
        self.assertEqual(ordem.status, StatusOrdemServico.RECEBIDA)
        progresso = ordem.resumo_progresso()
        self.assertEqual(progresso["total"], 3)
        self.assertEqual(progresso["manometros"], 2)
        self.assertEqual(progresso["valvulas"], 1)
        self.assertEqual(progresso["servicos"][ServicoSolicitado.CALIBRACAO], 2)
        self.assertEqual(progresso["servicos"][ServicoSolicitado.MANUTENCAO], 1)
        detalhe = self.client.get(reverse("servicos:detalhe_ordem", args=[ordem.pk]))
        self.assertContains(detalhe, "Metalúrgica Alfa")
        self.assertEqual(detalhe.context["progresso"]["manometros"], 2)
        self.assertEqual(detalhe.context["progresso"]["valvulas"], 1)
        self.assertContains(detalhe, "Calibração: 2")
        self.assertContains(detalhe, "Manutenção: 1")
        self.assertContains(detalhe, "Recebida")

        itens = {item.codigo_equipamento: item for item in ordem.itens.all()}
        itens["MAN-001"].aplicar_status(StatusItemOrdem.EM_EXECUCAO)
        itens["MAN-002"].aplicar_status(StatusItemOrdem.CONCLUIDO)
        ordem.refresh_from_db()
        progresso = ordem.resumo_progresso()
        self.assertEqual(progresso["concluidos"], 1)
        self.assertEqual(progresso["percentual"], 33)
        self.assertEqual(ordem.status, StatusOrdemServico.EM_EXECUCAO)
        detalhe = self.client.get(reverse("servicos:detalhe_ordem", args=[ordem.pk]))
        self.assertContains(detalhe, "1 de 3 itens concluídos")
        self.assertContains(detalhe, "33%")
        self.assertContains(detalhe, "Em execução")

        itens["MAN-001"].refresh_from_db()
        itens["VAL-001"].refresh_from_db()
        itens["MAN-001"].servico_solicitado = ServicoSolicitado.AJUSTE
        itens["MAN-001"].save(update_fields=["servico_solicitado"])
        itens["MAN-002"].servico_solicitado = ServicoSolicitado.AJUSTE
        itens["MAN-002"].save(update_fields=["servico_solicitado"])
        itens["MAN-001"].aplicar_status(StatusItemOrdem.CONCLUIDO)
        itens["VAL-001"].aplicar_status(StatusItemOrdem.CONCLUIDO)
        ordem.refresh_from_db()
        self.assertEqual(ordem.resumo_progresso()["percentual"], 100)
        self.assertEqual(ordem.status, StatusOrdemServico.CONCLUIDA)
        self.assertTrue(ordem.alterar_status(StatusOrdemServico.ENTREGUE)[0])

    def test_progresso_0_1_2_4(self):
        ordem = self._os(StatusOrdemServico.RECEBIDA)
        itens = [
            self._item_man(ordem, self.man_001),
            self._item_man(ordem, self.man_002),
            self._item_val(ordem, self.val_001),
            self._item_val(ordem, self.val_002),
        ]
        self.assertEqual(ordem.resumo_progresso()["percentual"], 0)
        self.assertEqual(ordem.resumo_progresso()["concluidos"], 0)
        itens[0].aplicar_status(StatusItemOrdem.CONCLUIDO, sincronizar=False)
        self.assertEqual(ordem.resumo_progresso()["concluidos"], 1)
        self.assertEqual(ordem.resumo_progresso()["percentual"], 25)
        itens[1].aplicar_status(StatusItemOrdem.CONCLUIDO, sincronizar=False)
        self.assertEqual(ordem.resumo_progresso()["concluidos"], 2)
        self.assertEqual(ordem.resumo_progresso()["percentual"], 50)
        itens[2].aplicar_status(StatusItemOrdem.CONCLUIDO, sincronizar=False)
        itens[3].aplicar_status(StatusItemOrdem.CONCLUIDO, sincronizar=False)
        self.assertEqual(ordem.resumo_progresso()["concluidos"], 4)
        self.assertEqual(ordem.resumo_progresso()["percentual"], 100)

    def test_bloqueios_recebimento_conclusao_entrega_e_item_cancelado(self):
        vazia = self._os()
        ok, erro = vazia.alterar_status(StatusOrdemServico.RECEBIDA)
        self.assertFalse(ok)
        self.assertIn("pelo menos um item", erro)

        ordem = self._os()
        ativo = self._item_man(
            ordem, self.man_001, servico=ServicoSolicitado.AJUSTE
        )
        cancelado = self._item_val(ordem, self.val_001)
        cancelado.aplicar_status(StatusItemOrdem.CANCELADO, sincronizar=False)
        self.assertTrue(ordem.alterar_status(StatusOrdemServico.RECEBIDA)[0])
        progresso = ordem.resumo_progresso()
        self.assertEqual(progresso["total"], 1)
        ok, erro = ordem.alterar_status(StatusOrdemServico.CONCLUIDA)
        self.assertFalse(ok)
        self.assertIn("pendentes", erro)
        ativo.aplicar_status(StatusItemOrdem.CONCLUIDO)
        ordem.refresh_from_db()
        if ordem.status != StatusOrdemServico.CONCLUIDA:
            self.assertTrue(ordem.alterar_status(StatusOrdemServico.CONCLUIDA)[0])
        self.assertTrue(ordem.alterar_status(StatusOrdemServico.ENTREGUE)[0])
        self.assertFalse(ordem.pode_editar)
        editar = self.client.get(reverse("servicos:editar_ordem", args=[ordem.pk]))
        self.assertRedirects(editar, reverse("servicos:detalhe_ordem", args=[ordem.pk]))
        self.client.post(
            reverse("servicos:iniciar_item_ordem", args=[ativo.pk]),
        )
        ativo.refresh_from_db()
        self.assertEqual(ativo.status, StatusItemOrdem.CONCLUIDO)

    def test_item_nao_aponta_para_dois_equipamentos(self):
        ordem = self._os()
        item = ItemOrdemServico(
            ordem_servico=ordem,
            instrumento=self.man_001,
            valvula=self.val_001,
        )
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_calibracao_nova_fica_vinculada_ao_item_e_os(self):
        ordem = self._os()
        item = self._item_man(ordem, self.man_001)
        ordem.alterar_status(StatusOrdemServico.RECEBIDA)
        response = self.client.post(
            reverse("servicos:cadastrar_calibracao") + f"?item={item.pk}",
            {
                "instrumento": self.man_001.pk,
                "item_ordem_servico": item.pk,
                "data_calibracao": "2026-09-13",
                "criterio_aceitacao": "Critério interno",
                "tolerancia": "0.10",
                "pontos-TOTAL_FORMS": "1",
                "pontos-INITIAL_FORMS": "0",
                "pontos-MIN_NUM_FORMS": "0",
                "pontos-MAX_NUM_FORMS": "1000",
                "pontos-0-ordem": "1",
                "pontos-0-valor_referencia": "1",
                "pontos-0-indicacao_instrumento": "1",
                "pontos-0-observacoes": "",
            },
        )
        calibracao = Calibracao.objects.get()
        self.assertRedirects(
            response, reverse("servicos:detalhe_calibracao", args=[calibracao.pk])
        )
        self.assertEqual(calibracao.item_ordem_servico_id, item.pk)
        self.assertEqual(calibracao.instrumento_id, self.man_001.pk)
        item.refresh_from_db()
        ordem.refresh_from_db()
        self.assertEqual(item.status, StatusItemOrdem.EM_EXECUCAO)
        self.assertEqual(ordem.status, StatusOrdemServico.EM_EXECUCAO)
        fila = self.client.get(reverse("servicos:fila_ordens"))
        self.assertContains(fila, ordem.numero)
        self.assertContains(fila, "MAN-001")
        self.assertContains(fila, "Recebidos")

    def test_maquina_status_os(self):
        ordem = self._os()
        item = self._item_val(ordem, self.val_001)
        self.assertEqual(ordem.status, StatusOrdemServico.ABERTA)
        self.assertTrue(ordem.alterar_status(StatusOrdemServico.RECEBIDA)[0])
        item.aplicar_status(StatusItemOrdem.EM_EXECUCAO)
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOrdemServico.EM_EXECUCAO)
        item.aplicar_status(StatusItemOrdem.AGUARDANDO_REVISAO)
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOrdemServico.AGUARDANDO_REVISAO)
        item.aplicar_status(StatusItemOrdem.CONCLUIDO)
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOrdemServico.CONCLUIDA)
        self.assertTrue(ordem.alterar_status(StatusOrdemServico.ENTREGUE)[0])
        cancelavel = self._os()
        self._item_val(cancelavel, self.val_002)
        self.assertTrue(cancelavel.alterar_status(StatusOrdemServico.CANCELADA)[0])
        self.assertEqual(cancelavel.status, StatusOrdemServico.CANCELADA)

    def test_detalhe_item_valvula_nao_abre_calibracao(self):
        ordem = self._os()
        item = self._item_val(ordem, self.val_001, condicao="Com corrosão")
        pagina = self.client.get(reverse("servicos:detalhe_item_ordem", args=[item.pk]))
        self.assertContains(pagina, "VAL-001")
        self.assertContains(pagina, "Manutenção")
        self.assertContains(pagina, "Com corrosão")
        self.assertNotContains(pagina, "Abrir calibração")
        self.assertContains(pagina, "Abrir execução")

    def test_item_recebido_sem_calibracao_permite_iniciar_servico(self):
        ordem = self._os(StatusOrdemServico.RECEBIDA)
        item = self._item_man(ordem, self.man_001)
        self.assertEqual(item.status, StatusItemOrdem.RECEBIDO)
        self.assertIsNone(item.calibracao_atual)
        self.assertTrue(item.pode_iniciar_calibracao)
        self.assertEqual(ordem.proximo_passo(), "Iniciar o serviço de MAN-001.")
        pagina = self.client.get(reverse("servicos:detalhe_item_ordem", args=[item.pk]))
        self.assertContains(pagina, "Iniciar serviço")
        self.assertContains(pagina, "Ainda não há calibração vinculada")
        os_pagina = self.client.get(reverse("servicos:detalhe_ordem", args=[ordem.pk]))
        self.assertContains(os_pagina, "Iniciar serviço")
        self.assertContains(os_pagina, f"{ordem.numero}")
        self.assertEqual(os_pagina.context["ordem"].status, StatusOrdemServico.RECEBIDA)
        self.assertContains(os_pagina, "Recebida")

    def test_iniciar_servico_cria_calibracao_e_avanca_status(self):
        ordem = self._os(StatusOrdemServico.RECEBIDA)
        item = self._item_man(ordem, self.man_001)
        response = self.client.post(
            reverse("servicos:iniciar_item_ordem", args=[item.pk])
        )
        calibracao = Calibracao.objects.get()
        self.assertRedirects(
            response, reverse("servicos:editar_calibracao", args=[calibracao.pk])
        )
        item.refresh_from_db()
        ordem.refresh_from_db()
        self.assertEqual(calibracao.item_ordem_servico_id, item.pk)
        self.assertEqual(calibracao.instrumento_id, self.man_001.pk)
        self.assertEqual(calibracao.status, StatusCalibracao.RASCUNHO)
        self.assertEqual(item.status, StatusItemOrdem.EM_EXECUCAO)
        self.assertEqual(ordem.status, StatusOrdemServico.EM_EXECUCAO)

    def test_iniciar_servico_nao_duplica_calibracao(self):
        ordem = self._os(StatusOrdemServico.RECEBIDA)
        item = self._item_man(ordem, self.man_001)
        self.client.post(reverse("servicos:iniciar_item_ordem", args=[item.pk]))
        self.client.post(reverse("servicos:iniciar_item_ordem", args=[item.pk]))
        self.assertEqual(Calibracao.objects.filter(item_ordem_servico=item).count(), 1)
        item.refresh_from_db()
        self.assertEqual(item.status, StatusItemOrdem.EM_EXECUCAO)

    def test_item_em_execucao_nao_inicia_segunda_calibracao(self):
        ordem = self._os(StatusOrdemServico.RECEBIDA)
        item = self._item_man(ordem, self.man_001)
        self.client.post(reverse("servicos:iniciar_item_ordem", args=[item.pk]))
        item.refresh_from_db()
        self.assertEqual(item.status, StatusItemOrdem.EM_EXECUCAO)
        self.assertFalse(item.pode_iniciar_calibracao)
        self.client.post(reverse("servicos:iniciar_item_ordem", args=[item.pk]))
        self.assertEqual(Calibracao.objects.count(), 1)

    def test_valvula_nao_inicia_fluxo_de_calibracao(self):
        ordem = self._os(StatusOrdemServico.RECEBIDA)
        item = self._item_val(ordem, self.val_001)
        with self.assertRaises(ValidationError):
            Calibracao.abrir_para_item(item, self.user)
        self.client.post(reverse("servicos:iniciar_item_ordem", args=[item.pk]))
        self.assertFalse(Calibracao.objects.exists())
        pagina = self.client.get(reverse("servicos:detalhe_item_ordem", args=[item.pk]))
        self.assertNotContains(pagina, "Iniciar serviço")

    def test_os_recebida_nao_fica_aguardando_revisao(self):
        ordem = self._os(StatusOrdemServico.RECEBIDA)
        item = self._item_man(ordem, self.man_001)
        ordem.status = StatusOrdemServico.AGUARDANDO_REVISAO
        ordem.save(update_fields=["status"])
        self.assertEqual(item.status, StatusItemOrdem.RECEBIDO)
        self.assertIsNone(item.calibracao_atual)
        pagina = self.client.get(reverse("servicos:detalhe_ordem", args=[ordem.pk]))
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOrdemServico.RECEBIDA)
        self.assertContains(pagina, "Recebida")
        self.assertContains(pagina, "Iniciar o serviço de MAN-001.")
        self.assertEqual(ordem.proximo_passo(), "Iniciar o serviço de MAN-001.")
        self.assertNotEqual(ordem.status, StatusOrdemServico.AGUARDANDO_REVISAO)


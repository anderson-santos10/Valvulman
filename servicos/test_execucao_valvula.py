from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from clientes.models import Cliente

from .models import (
    Calibracao,
    ExecucaoValvula,
    Instrumento,
    ItemOrdemServico,
    OrdemServico,
    PontoCalibracao,
    RelatorioTecnico,
    ResultadoCalibracao,
    ResultadoExecucaoValvula,
    ServicoSolicitado,
    StatusCalibracao,
    StatusExecucaoValvula,
    StatusItemOrdem,
    StatusOrdemServico,
    TipoEquipamento,
    TipoInstrumento,
    UnidadePressao,
    Valvula,
    ValvulaRelatorio,
)


class ExecucaoValvulaTests(TestCase):
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
            faixa_minima=Decimal("0"),
            faixa_maxima=Decimal("10"),
            unidade=UnidadePressao.BAR,
            tipo=TipoInstrumento.MANOMETRO,
        )
        self.man_002 = Instrumento.objects.create(
            cliente=self.cliente,
            codigo="MAN-002",
            faixa_minima=Decimal("0"),
            faixa_maxima=Decimal("16"),
            unidade=UnidadePressao.BAR,
            tipo=TipoInstrumento.MANOMETRO,
        )
        self.val_001 = Valvula.objects.create(
            cliente=self.cliente,
            codigo="VAL-001",
            tag="PSV-101",
            numero_serie="SN-VAL-1",
            fabricante="Spirax",
            modelo="SV-100",
            diametro_nominal='2"',
            pressao_ajuste=Decimal("8"),
            unidade_pressao=UnidadePressao.BAR,
        )
        self.val_002 = Valvula.objects.create(
            cliente=self.cliente,
            codigo="VAL-002",
            tag="PSV-102",
            fabricante="Spirax",
            modelo="SV-200",
            diametro_nominal='2"',
            pressao_ajuste=Decimal("10"),
            unidade_pressao=UnidadePressao.BAR,
        )

    def _os(self, status=StatusOrdemServico.RECEBIDA):
        return OrdemServico.criar(
            cliente=self.cliente,
            data_entrada=date(2026, 9, 13),
            status=status,
        )

    def _item_man(self, ordem, instrumento):
        return ItemOrdemServico.objects.create(
            ordem_servico=ordem,
            tipo_equipamento=TipoEquipamento.INSTRUMENTO,
            instrumento=instrumento,
            servico_solicitado=ServicoSolicitado.CALIBRACAO,
        )

    def _item_val(self, ordem, valvula, servico=ServicoSolicitado.MANUTENCAO):
        return ItemOrdemServico.objects.create(
            ordem_servico=ordem,
            tipo_equipamento=TipoEquipamento.VALVULA,
            valvula=valvula,
            servico_solicitado=servico,
        )

    def _dados_execucao(self, resultado=ResultadoExecucaoValvula.APROVADO):
        return {
            "data_inicio": "2026-09-13",
            "data_fim": "2026-09-13",
            "descricao_servico": "Serviço realizado na válvula.",
            "observacoes": "Observação da execução.",
            "resultado": resultado,
            "observacoes_revisao": "",
        }

    def _concluir_calibracao(self, item):
        calibracao = Calibracao.objects.create(
            instrumento=item.instrumento,
            item_ordem_servico=item,
            data_calibracao=date(2026, 9, 13),
            criterio_aceitacao="Critério interno",
            tolerancia=Decimal("0.10"),
        )
        PontoCalibracao.objects.create(
            calibracao=calibracao,
            ordem=1,
            valor_referencia=Decimal("1"),
            indicacao_instrumento=Decimal("1"),
        )
        calibracao.registrar_execucao(self.user)
        calibracao.registrar_revisao(self.user)
        calibracao.status = StatusCalibracao.CONCLUIDA
        calibracao.aplicar_resultado_oficial()
        calibracao.save()
        item.sincronizar_com_calibracao(calibracao)
        return calibracao

    def _fluxo_http(self, item, resultado=ResultadoExecucaoValvula.APROVADO):
        abrir = self.client.post(
            reverse("servicos:abrir_execucao_valvula", args=[item.pk])
        )
        self.assertRedirects(
            abrir, reverse("servicos:detalhe_execucao_valvula", args=[item.pk])
        )
        dados = self._dados_execucao(resultado)
        salvar = self.client.post(
            reverse("servicos:salvar_execucao_valvula", args=[item.pk]),
            dados,
        )
        self.assertRedirects(
            salvar, reverse("servicos:detalhe_execucao_valvula", args=[item.pk])
        )
        item.refresh_from_db()
        self.assertEqual(item.status, StatusItemOrdem.EM_EXECUCAO)
        self.assertEqual(
            item.execucao_valvula_atual.status, StatusExecucaoValvula.RASCUNHO
        )
        revisao = self.client.post(
            reverse("servicos:enviar_revisao_execucao_valvula", args=[item.pk]),
            dados,
        )
        self.assertRedirects(
            revisao, reverse("servicos:detalhe_execucao_valvula", args=[item.pk])
        )
        item.refresh_from_db()
        self.assertEqual(item.status, StatusItemOrdem.AGUARDANDO_REVISAO)
        self.assertEqual(
            item.execucao_valvula_atual.status, StatusExecucaoValvula.RASCUNHO
        )
        revisar = self.client.post(
            reverse("servicos:revisar_execucao_valvula", args=[item.pk]),
            {**dados, "observacoes_revisao": "Revisão ok."},
        )
        self.assertRedirects(
            revisar, reverse("servicos:detalhe_execucao_valvula", args=[item.pk])
        )
        item.refresh_from_db()
        self.assertTrue(item.execucao_valvula_atual.esta_revisada)
        concluir = self.client.post(
            reverse("servicos:concluir_execucao_valvula", args=[item.pk])
        )
        self.assertRedirects(
            concluir, reverse("servicos:detalhe_execucao_valvula", args=[item.pk])
        )
        item.refresh_from_db()
        execucao = item.execucao_valvula_atual
        self.assertEqual(execucao.status, StatusExecucaoValvula.CONCLUIDA)
        self.assertEqual(execucao.resultado, resultado)
        self.assertEqual(item.status, StatusItemOrdem.CONCLUIDO)
        return execucao

    def test_criar_execucao_para_valvula(self):
        ordem = self._os()
        item = self._item_val(ordem, self.val_001)
        execucao, criada = ExecucaoValvula.abrir_para_item(item, self.user)
        self.assertTrue(criada)
        self.assertEqual(execucao.item_ordem_servico_id, item.pk)
        self.assertEqual(execucao.valvula_codigo, "VAL-001")
        self.assertEqual(execucao.valvula_tag, "PSV-101")
        self.assertEqual(execucao.valvula_pressao_ajuste, Decimal("8"))
        self.assertEqual(execucao.status, StatusExecucaoValvula.RASCUNHO)
        item.refresh_from_db()
        self.assertEqual(item.status, StatusItemOrdem.EM_EXECUCAO)
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOrdemServico.EM_EXECUCAO)

    def test_criar_execucao_para_manometro_falha(self):
        ordem = self._os()
        item = self._item_man(ordem, self.man_001)
        with self.assertRaises(ValidationError):
            ExecucaoValvula.abrir_para_item(item, self.user)
        execucao = ExecucaoValvula(item_ordem_servico=item)
        with self.assertRaises(ValidationError):
            execucao.save()
        post = self.client.post(
            reverse("servicos:abrir_execucao_valvula", args=[item.pk])
        )
        self.assertRedirects(
            post, reverse("servicos:detalhe_item_ordem", args=[item.pk])
        )
        self.assertFalse(ExecucaoValvula.objects.exists())

    def test_mesmo_item_nao_pode_ter_duas_execucoes(self):
        ordem = self._os()
        item = self._item_val(ordem, self.val_001)
        primeira, _ = ExecucaoValvula.abrir_para_item(item, self.user)
        segunda, criada = ExecucaoValvula.abrir_para_item(item, self.user)
        self.assertFalse(criada)
        self.assertEqual(primeira.pk, segunda.pk)
        duplicada = ExecucaoValvula(
            item_ordem_servico=item,
            data_inicio=date(2026, 9, 13),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                duplicada.save()

    def test_fluxo_manutencao(self):
        ordem = self._os()
        item = self._item_val(ordem, self.val_001, ServicoSolicitado.MANUTENCAO)
        execucao = self._fluxo_http(item)
        self.assertTrue(execucao.eh_manutencao)
        pagina = self.client.get(
            reverse("servicos:detalhe_execucao_valvula", args=[item.pk])
        )
        self.assertContains(pagina, "Descrição do serviço realizado")
        self.assertContains(pagina, "VAL-001")
        self.assertContains(pagina, "Manutenção")

    def test_fluxo_ensaio_sem_medicoes_psv(self):
        ordem = self._os()
        item = self._item_val(ordem, self.val_002, ServicoSolicitado.ENSAIO)
        execucao = self._fluxo_http(item, ResultadoExecucaoValvula.REPROVADO)
        self.assertTrue(execucao.eh_ensaio)
        pagina = self.client.get(
            reverse("servicos:detalhe_execucao_valvula", args=[item.pk])
        )
        self.assertContains(
            pagina,
            "Dados específicos do ensaio técnico serão registrados em etapa posterior.",
        )
        self.assertNotContains(pagina, "pressão de abertura")
        self.assertEqual(execucao.resultado, ResultadoExecucaoValvula.REPROVADO)

    def test_concluir_item_sem_execucao_bloqueado(self):
        ordem = self._os()
        item = self._item_val(ordem, self.val_001)
        response = self.client.post(
            reverse("servicos:concluir_item_ordem", args=[item.pk])
        )
        self.assertRedirects(
            response, reverse("servicos:detalhe_item_ordem", args=[item.pk])
        )
        item.refresh_from_db()
        self.assertNotEqual(item.status, StatusItemOrdem.CONCLUIDO)

    def test_concluir_item_com_rascunho_bloqueado(self):
        ordem = self._os()
        item = self._item_val(ordem, self.val_001)
        ExecucaoValvula.abrir_para_item(item, self.user)
        response = self.client.post(
            reverse("servicos:concluir_item_ordem", args=[item.pk])
        )
        item.refresh_from_db()
        self.assertEqual(item.execucao_valvula_atual.status, StatusExecucaoValvula.RASCUNHO)
        self.assertNotEqual(item.status, StatusItemOrdem.CONCLUIDO)
        self.assertRedirects(
            response, reverse("servicos:detalhe_item_ordem", args=[item.pk])
        )

    def test_enviar_revisao_sem_resultado_bloqueado(self):
        ordem = self._os()
        item = self._item_val(ordem, self.val_001)
        ExecucaoValvula.abrir_para_item(item, self.user)
        dados = self._dados_execucao(ResultadoExecucaoValvula.PENDENTE)
        response = self.client.post(
            reverse("servicos:enviar_revisao_execucao_valvula", args=[item.pk]),
            dados,
        )
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.status, StatusItemOrdem.EM_EXECUCAO)
        concluir = self.client.post(
            reverse("servicos:concluir_execucao_valvula", args=[item.pk])
        )
        self.assertRedirects(
            concluir, reverse("servicos:detalhe_execucao_valvula", args=[item.pk])
        )
        self.assertEqual(
            item.execucao_valvula_atual.status, StatusExecucaoValvula.RASCUNHO
        )

    def test_item_legado_concluido_sem_execucao_preservado(self):
        ordem = self._os()
        item = self._item_val(ordem, self.val_001)
        item.aplicar_status(StatusItemOrdem.CONCLUIDO)
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOrdemServico.CONCLUIDA)
        self.assertIsNone(item.execucao_valvula_atual)

    def test_os_mista_uma_unica_os(self):
        ordem = self._os()
        man1 = self._item_man(ordem, self.man_001)
        man2 = self._item_man(ordem, self.man_002)
        val1 = self._item_val(ordem, self.val_001, ServicoSolicitado.MANUTENCAO)
        val2 = self._item_val(ordem, self.val_002, ServicoSolicitado.ENSAIO)
        cal1 = self._concluir_calibracao(man1)
        cal2 = self._concluir_calibracao(man2)
        self.assertEqual(cal1.resultado, ResultadoCalibracao.APROVADO)
        self.assertEqual(cal2.status, StatusCalibracao.CONCLUIDA)
        self._fluxo_http(val1)
        self._fluxo_http(val2)
        ordem.refresh_from_db()
        progresso = ordem.resumo_progresso()
        self.assertEqual(OrdemServico.objects.count(), 1)
        self.assertEqual(progresso["total"], 4)
        self.assertEqual(progresso["concluidos"], 4)
        self.assertEqual(progresso["percentual"], 100)
        self.assertEqual(ordem.status, StatusOrdemServico.CONCLUIDA)
        self.assertEqual(ordem.itens.count(), 4)

    def test_historico_mostra_resultado_quando_existe_execucao(self):
        ordem = self._os()
        item = self._item_val(ordem, self.val_001)
        self._fluxo_http(item)
        pagina = self.client.get(
            reverse("servicos:detalhe_valvula", args=[self.val_001.pk])
        )
        self.assertContains(pagina, ordem.numero)
        self.assertContains(pagina, "Aprovado")
        self.assertContains(pagina, "Relatório técnico legado")

    def test_legado_relatorio_tecnico_intacto(self):
        relatorio = RelatorioTecnico.objects.create(
            cliente=self.cliente,
            numero_relatorio="RAT-LEGADO",
            setor="Caldeiras",
            data=date(2026, 1, 10),
        )
        ValvulaRelatorio.objects.create(
            relatorio=relatorio,
            valvula=self.val_001,
            item="1",
            numero_serie="SN-VAL-1",
            tag="PSV-101",
            servico="Manutenção",
        )
        self.assertEqual(self.val_001.itens_relatorio.count(), 1)
        pagina = self.client.get(
            reverse("servicos:detalhe_relatorio", args=[relatorio.pk])
        )
        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, "RAT-LEGADO")

    def test_snapshot_nao_muda_com_cadastro(self):
        ordem = self._os()
        item = self._item_val(ordem, self.val_001)
        execucao, _ = ExecucaoValvula.abrir_para_item(item, self.user)
        self.val_001.tag = "PSV-ALTERADA"
        self.val_001.save(update_fields=["tag"])
        execucao.refresh_from_db()
        self.assertEqual(execucao.valvula_tag, "PSV-101")

    def test_proximo_passo_abrir_execucao(self):
        ordem = self._os()
        self._item_val(ordem, self.val_001)
        self.assertEqual(ordem.proximo_passo(), "Abrir execução de VAL-001.")

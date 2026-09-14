from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from clientes.models import Cliente

from .models import (
    Calibracao,
    CertificadoCalibracao,
    Instrumento,
    ItemOrdemServico,
    OrdemServico,
    PontoCalibracao,
    ServicoSolicitado,
    StatusItemOrdem,
    StatusOrdemServico,
    TipoInstrumento,
    UnidadePressao,
)
from .test_calibracoes import preparar_conclusao


class OrdemServicoTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="operador",
            email="operador@example.com",
            password="senha-segura-123",
        )
        self.client.login(username="operador", password="senha-segura-123")
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
        self.instrumento_a = Instrumento.objects.create(
            cliente=self.cliente_a,
            codigo="MAN-001",
            tag="PI-01",
            numero_serie="SN-001",
            tipo=TipoInstrumento.MANOMETRO,
            faixa_minima=Decimal("0"),
            faixa_maxima=Decimal("10"),
            unidade=UnidadePressao.BAR,
        )
        self.instrumento_a2 = Instrumento.objects.create(
            cliente=self.cliente_a,
            codigo="MAN-002",
            tag="PI-02",
            numero_serie="SN-002",
            tipo=TipoInstrumento.MANOMETRO,
            faixa_minima=Decimal("0"),
            faixa_maxima=Decimal("16"),
            unidade=UnidadePressao.BAR,
        )
        self.instrumento_b = Instrumento.objects.create(
            cliente=self.cliente_b,
            codigo="MAN-099",
            tipo=TipoInstrumento.MANOMETRO,
            faixa_minima=Decimal("0"),
            faixa_maxima=Decimal("10"),
            unidade=UnidadePressao.BAR,
        )

    def _dados_itens(self, instrumentos, inicial=0):
        dados = {
            "itens-TOTAL_FORMS": str(len(instrumentos)),
            "itens-INITIAL_FORMS": str(inicial),
            "itens-MIN_NUM_FORMS": "0",
            "itens-MAX_NUM_FORMS": "1000",
        }
        for indice, instrumento in enumerate(instrumentos):
            prefixo = f"itens-{indice}"
            dados[f"{prefixo}-tipo_equipamento"] = "instrumento"
            dados[f"{prefixo}-instrumento"] = str(instrumento.pk)
            dados[f"{prefixo}-servico_solicitado"] = ServicoSolicitado.CALIBRACAO
            dados[f"{prefixo}-condicao_recebimento"] = "Bom estado"
            dados[f"{prefixo}-observacoes_recebimento"] = ""
            dados[f"{prefixo}-status"] = StatusItemOrdem.RECEBIDO
            dados[f"{prefixo}-observacoes"] = ""
            if getattr(instrumento, "item_id", None):
                dados[f"{prefixo}-id"] = str(instrumento.item_id)
        return dados

    def test_login_obrigatorio(self):
        self.client.logout()
        response = self.client.get(reverse("servicos:lista_ordens"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_cria_os_com_varios_itens_e_numero_unico(self):
        dados = {
            "cliente": self.cliente_a.pk,
            "data_entrada": "2026-09-09",
            "data_previsao_entrega": "2026-09-15",
            "solicitante": "João da Empresa ABC",
            "observacoes": "Entrada de manômetros",
        }
        dados.update(self._dados_itens([self.instrumento_a, self.instrumento_a2]))
        response = self.client.post(reverse("servicos:cadastrar_ordem"), dados)
        ordem = OrdemServico.objects.get()
        self.assertRedirects(response, reverse("servicos:detalhe_ordem", args=[ordem.pk]))
        self.assertEqual(ordem.numero, "OS-000001")
        self.assertEqual(ordem.status, StatusOrdemServico.RECEBIDA)
        self.assertEqual(ordem.itens.count(), 2)
        segunda = OrdemServico.criar(
            cliente=self.cliente_a,
            data_entrada=date(2026, 9, 10),
        )
        self.assertEqual(segunda.numero, "OS-000002")
        self.assertEqual(OrdemServico.objects.filter(numero="OS-000001").count(), 1)

    def test_rejeita_instrumento_de_outro_cliente(self):
        dados = {
            "cliente": self.cliente_a.pk,
            "data_entrada": "2026-09-09",
        }
        dados.update(self._dados_itens([self.instrumento_b]))
        response = self.client.post(reverse("servicos:cadastrar_ordem"), dados)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(OrdemServico.objects.exists())

    def test_fluxo_status_e_cancelamento(self):
        ordem = OrdemServico.criar(
            cliente=self.cliente_a,
            data_entrada=date(2026, 9, 9),
        )
        ItemOrdemServico.objects.create(
            ordem_servico=ordem,
            instrumento=self.instrumento_a,
            servico_solicitado=ServicoSolicitado.AJUSTE,
        )
        self.assertFalse(
            ordem.alterar_status(StatusOrdemServico.ENTREGUE)[0]
        )
        self.assertTrue(ordem.alterar_status(StatusOrdemServico.RECEBIDA)[0])
        self.assertTrue(ordem.alterar_status(StatusOrdemServico.EM_EXECUCAO)[0])
        self.assertTrue(ordem.alterar_status(StatusOrdemServico.AGUARDANDO_REVISAO)[0])
        item = ordem.itens.get()
        item.status = StatusItemOrdem.CONCLUIDO
        item.save(update_fields=["status"])
        ordem.refresh_from_db()
        self.assertTrue(ordem.alterar_status(StatusOrdemServico.CONCLUIDA)[0])
        self.assertTrue(ordem.alterar_status(StatusOrdemServico.ENTREGUE)[0])
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOrdemServico.ENTREGUE)
        self.assertEqual(ordem.data_entrega, timezone.localdate())
        self.assertFalse(ordem.pode_editar)
        get_entregar = self.client.get(
            reverse("servicos:entregar_ordem", args=[ordem.pk])
        )
        self.assertEqual(get_entregar.status_code, 405)

        cancelavel = OrdemServico.criar(
            cliente=self.cliente_a,
            data_entrada=date(2026, 9, 9),
        )
        self.client.post(reverse("servicos:cancelar_ordem", args=[cancelavel.pk]))
        cancelavel.refresh_from_db()
        self.assertEqual(cancelavel.status, StatusOrdemServico.CANCELADA)
        self.assertTrue(OrdemServico.objects.filter(pk=cancelavel.pk).exists())

    def test_nao_conclui_calibracao_em_rascunho(self):
        ordem = OrdemServico.criar(
            cliente=self.cliente_a,
            data_entrada=date(2026, 9, 9),
        )
        item = ItemOrdemServico.objects.create(
            ordem_servico=ordem,
            instrumento=self.instrumento_a,
        )
        Calibracao.objects.create(
            instrumento=self.instrumento_a,
            item_ordem_servico=item,
            data_calibracao=date(2026, 9, 9),
            criterio_aceitacao="Critério interno",
            tolerancia=Decimal("0.10"),
        )
        item.status = StatusItemOrdem.CONCLUIDO
        item.save(update_fields=["status"])
        ordem.alterar_status(StatusOrdemServico.EM_EXECUCAO)
        ok, erro = ordem.alterar_status(StatusOrdemServico.CONCLUIDA)
        self.assertFalse(ok)
        self.assertIn("não está concluída", erro)

    def test_calibracao_vinculada_ao_item_e_certificado_navegavel(self):
        ordem = OrdemServico.criar(
            cliente=self.cliente_a,
            data_entrada=date(2026, 9, 9),
        )
        item = ItemOrdemServico.objects.create(
            ordem_servico=ordem,
            instrumento=self.instrumento_a,
        )
        dados = {
            "instrumento": self.instrumento_b.pk,
            "item_ordem_servico": item.pk,
            "data_calibracao": "2026-09-09",
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
        }
        response = self.client.post(
            reverse("servicos:cadastrar_calibracao") + f"?item={item.pk}",
            dados,
        )
        calibracao = Calibracao.objects.get()
        self.assertRedirects(
            response,
            reverse("servicos:detalhe_calibracao", args=[calibracao.pk]),
        )
        self.assertEqual(calibracao.instrumento_id, self.instrumento_a.pk)
        self.assertEqual(calibracao.item_ordem_servico_id, item.pk)
        PontoCalibracao.objects.filter(calibracao=calibracao).delete()
        PontoCalibracao.objects.create(
            calibracao=calibracao,
            ordem=1,
            valor_referencia=Decimal("1"),
            indicacao_instrumento=Decimal("1"),
        )
        preparar_conclusao(calibracao, self.user)
        self.client.post(reverse("servicos:concluir_calibracao", args=[calibracao.pk]))
        self.client.post(reverse("servicos:emitir_certificado", args=[calibracao.pk]))
        certificado = CertificadoCalibracao.objects.get()
        detalhe = self.client.get(reverse("servicos:detalhe_ordem", args=[ordem.pk]))
        self.assertContains(detalhe, calibracao.numero)
        self.assertContains(detalhe, certificado.numero)
        ordem.refresh_from_db()
        if ordem.status != StatusOrdemServico.CONCLUIDA:
            ordem.alterar_status(StatusOrdemServico.EM_EXECUCAO)
            self.assertTrue(ordem.alterar_status(StatusOrdemServico.CONCLUIDA)[0])
        else:
            self.assertEqual(ordem.status, StatusOrdemServico.CONCLUIDA)

    def test_rejeita_vincular_calibracao_de_outro_instrumento(self):
        ordem = OrdemServico.criar(
            cliente=self.cliente_a,
            data_entrada=date(2026, 9, 9),
        )
        item = ItemOrdemServico.objects.create(
            ordem_servico=ordem,
            instrumento=self.instrumento_a,
        )
        outra = Calibracao.objects.create(
            instrumento=self.instrumento_a2,
            data_calibracao=date(2026, 9, 9),
        )
        response = self.client.post(
            reverse("servicos:vincular_calibracao_item", args=[item.pk]),
            {"calibracao": outra.pk},
        )
        self.assertRedirects(response, reverse("servicos:detalhe_ordem", args=[ordem.pk]))
        outra.refresh_from_db()
        self.assertIsNone(outra.item_ordem_servico_id)
        calibracao = Calibracao(
            instrumento=self.instrumento_a2,
            item_ordem_servico=item,
            data_calibracao=date(2026, 9, 9),
        )
        with self.assertRaises(ValidationError):
            calibracao.full_clean()

    def test_calibracao_antiga_sem_os_continua_valida(self):
        calibracao = Calibracao.objects.create(
            instrumento=self.instrumento_a,
            data_calibracao=date(2026, 9, 9),
            criterio_aceitacao="Critério interno",
            tolerancia=Decimal("0.10"),
        )
        self.assertIsNone(calibracao.item_ordem_servico_id)
        detalhe = self.client.get(
            reverse("servicos:detalhe_calibracao", args=[calibracao.pk])
        )
        self.assertEqual(detalhe.status_code, 200)

    def test_nao_edita_entregue(self):
        ordem = OrdemServico.criar(
            cliente=self.cliente_a,
            data_entrada=date(2026, 9, 9),
            status=StatusOrdemServico.ENTREGUE,
            data_entrega=date(2026, 9, 9),
        )
        response = self.client.get(reverse("servicos:editar_ordem", args=[ordem.pk]))
        self.assertRedirects(response, reverse("servicos:detalhe_ordem", args=[ordem.pk]))

    def test_impressao_exige_login_e_mostra_itens(self):
        ordem = OrdemServico.criar(
            cliente=self.cliente_a,
            data_entrada=date(2026, 9, 9),
        )
        ItemOrdemServico.objects.create(
            ordem_servico=ordem,
            instrumento=self.instrumento_a,
            condicao_recebimento="Bom estado",
        )
        pagina = self.client.get(reverse("servicos:imprimir_ordem", args=[ordem.pk]))
        self.assertContains(pagina, "OS-000001")
        self.assertContains(pagina, "MAN-001")
        self.client.logout()
        anonimo = self.client.get(reverse("servicos:imprimir_ordem", args=[ordem.pk]))
        self.assertEqual(anonimo.status_code, 302)

    def test_nao_entrega_os_aberta(self):
        ordem = OrdemServico.criar(
            cliente=self.cliente_a,
            data_entrada=date(2026, 9, 9),
        )
        self.client.post(reverse("servicos:entregar_ordem", args=[ordem.pk]))
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOrdemServico.ABERTA)
        self.assertIsNone(ordem.data_entrega)

    def test_cancelar_sem_csrf_e_rejeitado(self):
        ordem = OrdemServico.criar(
            cliente=self.cliente_a,
            data_entrada=date(2026, 9, 9),
        )
        cliente_csrf = Client(enforce_csrf_checks=True)
        cliente_csrf.login(username="operador", password="senha-segura-123")
        response = cliente_csrf.post(
            reverse("servicos:cancelar_ordem", args=[ordem.pk])
        )
        self.assertEqual(response.status_code, 403)
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOrdemServico.ABERTA)

    def test_lista_filtra_por_status_e_cliente(self):
        OrdemServico.criar(
            cliente=self.cliente_a,
            data_entrada=date(2026, 9, 9),
        )
        outra = OrdemServico.criar(
            cliente=self.cliente_b,
            data_entrada=date(2026, 9, 10),
        )
        outra.status = StatusOrdemServico.CANCELADA
        outra.save(update_fields=["status"])
        lista = self.client.get(
            reverse("servicos:lista_ordens"),
            {"status": StatusOrdemServico.CANCELADA, "cliente": self.cliente_b.pk},
        )
        self.assertContains(lista, "OS-000002")
        self.assertNotContains(lista, "OS-000001")

    def test_detalhe_cliente_mostra_os(self):
        ordem = OrdemServico.criar(
            cliente=self.cliente_a,
            data_entrada=date(2026, 9, 9),
        )
        detalhe = self.client.get(
            reverse("clientes:detalhe_cliente", args=[self.cliente_a.pk])
        )
        self.assertContains(detalhe, ordem.numero)
        self.assertContains(
            detalhe,
            reverse("servicos:cadastrar_ordem") + f"?cliente={self.cliente_a.pk}",
        )

    def test_os_preenche_e_preserva_snapshot_de_contato(self):
        self.cliente_a.contato_principal = "João da Silva"
        self.cliente_a.telefone = "(14) 99999-1111"
        self.cliente_a.email = "joao@empresa.com"
        self.cliente_a.save()
        pagina = self.client.get(
            reverse("servicos:cadastrar_ordem"),
            {"cliente": self.cliente_a.pk},
        )
        self.assertContains(pagina, "(14) 99999-1111")
        self.assertContains(pagina, "joao@empresa.com")
        json_cliente = self.client.get(
            reverse("servicos:instrumentos_por_cliente", args=[self.cliente_a.pk])
        )
        self.assertEqual(json_cliente.json()["cliente"]["telefone"], "(14) 99999-1111")
        dados = {
            "cliente": self.cliente_a.pk,
            "data_entrada": "2026-09-13",
            "solicitante": "Maria da Recepção",
            "telefone_solicitante": "(14) 98888-0000",
            "email_solicitante": "maria@empresa.com",
        }
        dados.update(self._dados_itens([self.instrumento_a]))
        self.client.post(reverse("servicos:cadastrar_ordem"), dados)
        ordem = OrdemServico.objects.get()
        self.assertEqual(ordem.solicitante, "Maria da Recepção")
        self.assertEqual(ordem.telefone_solicitante, "(14) 98888-0000")
        self.assertEqual(ordem.email_solicitante, "maria@empresa.com")
        self.cliente_a.telefone = "(14) 99999-2222"
        self.cliente_a.email = "novo@empresa.com"
        self.cliente_a.save()
        ordem.refresh_from_db()
        self.assertEqual(ordem.telefone_solicitante, "(14) 98888-0000")
        self.assertEqual(ordem.email_solicitante, "maria@empresa.com")
        detalhe = self.client.get(reverse("servicos:detalhe_ordem", args=[ordem.pk]))
        self.assertContains(detalhe, "(14) 98888-0000")
        self.assertNotContains(detalhe, "(14) 99999-2222")

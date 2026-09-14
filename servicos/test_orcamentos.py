from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from clientes.models import Cliente

from .models import (
    Instrumento,
    ItemOrcamento,
    ItemOrdemServico,
    Orcamento,
    OrdemServico,
    ServicoSolicitado,
    StatusItemOrdem,
    StatusOrcamento,
    StatusOrdemServico,
    TipoEquipamento,
    TipoInstrumento,
    UnidadePressao,
    Valvula,
)


class OrcamentoTests(TestCase):
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
        self.instrumento_b = Instrumento.objects.create(
            cliente=self.cliente_b,
            codigo="MAN-099",
            tipo=TipoInstrumento.MANOMETRO,
            faixa_minima=Decimal("0"),
            faixa_maxima=Decimal("10"),
            unidade=UnidadePressao.BAR,
        )
        self.instrumento_a2 = Instrumento.objects.create(
            cliente=self.cliente_a,
            codigo="MAN-002",
            tipo=TipoInstrumento.MANOMETRO,
            faixa_minima=Decimal("0"),
            faixa_maxima=Decimal("16"),
            unidade=UnidadePressao.BAR,
        )
        self.valvula_a = Valvula.objects.create(
            cliente=self.cliente_a,
            codigo="VAL-001",
            fabricante="Spirax",
            modelo="SV-100",
            diametro_nominal='2"',
            pressao_ajuste=Decimal("8"),
            unidade_pressao=UnidadePressao.BAR,
        )
        self.valvula_a2 = Valvula.objects.create(
            cliente=self.cliente_a,
            codigo="VAL-002",
            fabricante="Spirax",
            modelo="SV-200",
            diametro_nominal='2"',
            pressao_ajuste=Decimal("10"),
            unidade_pressao=UnidadePressao.BAR,
        )

    def _item(self, orcamento, instrumento=None, **extra):
        dados = {
            "orcamento": orcamento,
            "servico": ServicoSolicitado.CALIBRACAO,
            "instrumento": instrumento,
            "descricao": extra.pop("descricao", "Calibração de manômetro 0–10 bar."),
            "quantidade": extra.pop("quantidade", 1),
            "valor_unitario": extra.pop("valor_unitario", Decimal("150.00")),
            "desconto": extra.pop("desconto", Decimal("0.00")),
            "ordem": extra.pop("ordem", 1),
        }
        dados.update(extra)
        item = ItemOrcamento(**dados)
        item.full_clean()
        item.save()
        return item

    def _dados_formset(self, instrumento, valor="150.00"):
        return {
            "itens-TOTAL_FORMS": "1",
            "itens-INITIAL_FORMS": "0",
            "itens-MIN_NUM_FORMS": "0",
            "itens-MAX_NUM_FORMS": "1000",
            "itens-0-servico": ServicoSolicitado.CALIBRACAO,
            "itens-0-tipo_equipamento": TipoEquipamento.INSTRUMENTO,
            "itens-0-instrumento": str(instrumento.pk) if instrumento else "",
            "itens-0-descricao": "Calibração de manômetro 0–10 bar.",
            "itens-0-quantidade": "1",
            "itens-0-valor_unitario": valor,
            "itens-0-desconto": "0.00",
            "itens-0-ordem": "1",
        }

    def test_login_obrigatorio(self):
        self.client.logout()
        response = self.client.get(reverse("servicos:lista_orcamentos"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_numero_automatico_e_unico(self):
        primeiro = Orcamento.criar(
            cliente=self.cliente_a,
            data_emissao=self.hoje,
        )
        segundo = Orcamento.criar(
            cliente=self.cliente_a,
            data_emissao=self.hoje,
        )
        self.assertEqual(primeiro.numero, "ORC-000001")
        self.assertEqual(segundo.numero, "ORC-000002")
        self.assertEqual(Orcamento.objects.filter(numero="ORC-000001").count(), 1)

    def test_calculo_item_e_total(self):
        orcamento = Orcamento.criar(cliente=self.cliente_a, data_emissao=self.hoje)
        self._item(
            orcamento,
            self.instrumento_a,
            quantidade=2,
            valor_unitario=Decimal("100.00"),
            desconto=Decimal("10.00"),
        )
        totais = orcamento.totais()
        self.assertEqual(totais["subtotal"], Decimal("200.00"))
        self.assertEqual(totais["desconto"], Decimal("10.00"))
        self.assertEqual(totais["total"], Decimal("190.00"))

    def test_rejeita_quantidade_e_valores_invalidos(self):
        orcamento = Orcamento.criar(cliente=self.cliente_a, data_emissao=self.hoje)
        with self.assertRaises(ValidationError):
            self._item(orcamento, quantidade=0)
        with self.assertRaises(ValidationError):
            self._item(orcamento, valor_unitario=Decimal("-1.00"))

    def test_rejeita_instrumento_de_outro_cliente(self):
        orcamento = Orcamento.criar(cliente=self.cliente_a, data_emissao=self.hoje)
        with self.assertRaises(ValidationError):
            self._item(orcamento, self.instrumento_b)
        orcamento.delete()
        dados = {
            "cliente": self.cliente_a.pk,
            "data_emissao": self.hoje.isoformat(),
        }
        dados.update(self._dados_formset(self.instrumento_b))
        response = self.client.post(reverse("servicos:cadastrar_orcamento"), dados)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Orcamento.objects.exists())

    def test_fluxo_status_e_get_nao_altera(self):
        orcamento = Orcamento.criar(cliente=self.cliente_a, data_emissao=self.hoje)
        self.assertFalse(orcamento.alterar_status(StatusOrcamento.APROVADO)[0])
        self._item(orcamento, self.instrumento_a)
        self.assertTrue(orcamento.alterar_status(StatusOrcamento.ENVIADO)[0])
        get_aprovar = self.client.get(
            reverse("servicos:aprovar_orcamento", args=[orcamento.pk])
        )
        self.assertEqual(get_aprovar.status_code, 405)
        orcamento.refresh_from_db()
        self.assertEqual(orcamento.status, StatusOrcamento.ENVIADO)
        self.assertTrue(orcamento.alterar_status(StatusOrcamento.APROVADO)[0])

    def test_nao_aprova_sem_itens_nem_expirado(self):
        vazio = Orcamento.criar(cliente=self.cliente_a, data_emissao=self.hoje)
        self.assertFalse(vazio.alterar_status(StatusOrcamento.ENVIADO)[0])
        expirado = Orcamento.criar(
            cliente=self.cliente_a,
            data_emissao=self.hoje - timedelta(days=10),
            data_validade=self.hoje - timedelta(days=1),
        )
        self._item(expirado, self.instrumento_a)
        self.assertTrue(expirado.alterar_status(StatusOrcamento.ENVIADO)[0])
        self.assertTrue(expirado.prazo_expirado)
        self.assertFalse(expirado.alterar_status(StatusOrcamento.APROVADO)[0])
        recusado = Orcamento.criar(cliente=self.cliente_a, data_emissao=self.hoje)
        self._item(recusado, self.instrumento_a)
        recusado.alterar_status(StatusOrcamento.ENVIADO)
        recusado.alterar_status(StatusOrcamento.RECUSADO)
        self.assertFalse(recusado.alterar_status(StatusOrcamento.APROVADO)[0])

    def test_csrf_e_cancelamento_preserva_registro(self):
        orcamento = Orcamento.criar(cliente=self.cliente_a, data_emissao=self.hoje)
        cliente_csrf = Client(enforce_csrf_checks=True)
        cliente_csrf.login(username="operador", password="senha-segura-123")
        response = cliente_csrf.post(
            reverse("servicos:cancelar_orcamento", args=[orcamento.pk])
        )
        self.assertEqual(response.status_code, 403)
        self.client.post(reverse("servicos:cancelar_orcamento", args=[orcamento.pk]))
        orcamento.refresh_from_db()
        self.assertEqual(orcamento.status, StatusOrcamento.CANCELADO)
        self.assertTrue(Orcamento.objects.filter(pk=orcamento.pk).exists())

    def test_snapshot_nao_muda_com_cadastro(self):
        orcamento = Orcamento.criar(cliente=self.cliente_a, data_emissao=self.hoje)
        self._item(orcamento, self.instrumento_a)
        orcamento.alterar_status(StatusOrcamento.ENVIADO)
        self.cliente_a.nome = "Empresa ABC Alterada"
        self.cliente_a.cnpj = "00.000.000/0001-91"
        self.cliente_a.save()
        self.instrumento_a.codigo = "MAN-999"
        self.instrumento_a.save()
        orcamento.refresh_from_db()
        item = orcamento.itens.get()
        self.assertEqual(orcamento.cliente_nome_exibicao, "Empresa ABC")
        self.assertEqual(orcamento.cliente_documento_exibicao, "11.222.333/0001-81")
        self.assertEqual(item.instrumento_codigo_snapshot, "MAN-001")

    def test_gerar_os_fluxo_completo_sem_duplicar(self):
        dados = {
            "cliente": self.cliente_a.pk,
            "data_emissao": self.hoje.isoformat(),
            "condicoes_comerciais": "Pagamento em 30 dias.",
            "observacoes": "Proposta de calibração.",
        }
        dados.update(self._dados_formset(self.instrumento_a))
        criar = self.client.post(reverse("servicos:cadastrar_orcamento"), dados)
        orcamento = Orcamento.objects.get()
        self.assertRedirects(
            criar, reverse("servicos:detalhe_orcamento", args=[orcamento.pk])
        )
        self.client.post(reverse("servicos:enviar_orcamento", args=[orcamento.pk]))
        self.client.post(reverse("servicos:aprovar_orcamento", args=[orcamento.pk]))
        gerar = self.client.post(
            reverse("servicos:gerar_os_orcamento", args=[orcamento.pk])
        )
        ordem = OrdemServico.objects.get()
        self.assertRedirects(gerar, reverse("servicos:detalhe_ordem", args=[ordem.pk]))
        self.assertEqual(ordem.cliente_id, self.cliente_a.pk)
        self.assertEqual(ordem.orcamento_id, orcamento.pk)
        item_os = ItemOrdemServico.objects.get()
        self.assertEqual(item_os.instrumento_id, self.instrumento_a.pk)
        self.assertEqual(item_os.servico_solicitado, ServicoSolicitado.CALIBRACAO)
        self.assertEqual(ordem.status, StatusOrdemServico.RECEBIDA)
        segunda = self.client.post(
            reverse("servicos:gerar_os_orcamento", args=[orcamento.pk])
        )
        self.assertEqual(OrdemServico.objects.count(), 1)
        self.assertRedirects(segunda, reverse("servicos:detalhe_ordem", args=[ordem.pk]))
        rascunho = Orcamento.criar(cliente=self.cliente_a, data_emissao=self.hoje)
        self._item(rascunho, self.instrumento_a)
        ordem2, erro = rascunho.gerar_ordem_servico()
        self.assertIsNone(ordem2)
        self.assertIn("aprovado", erro.lower())

    def test_impressao_login_404_e_conteudo(self):
        orcamento = Orcamento.criar(cliente=self.cliente_a, data_emissao=self.hoje)
        self._item(orcamento, self.instrumento_a)
        pagina = self.client.get(
            reverse("servicos:imprimir_orcamento", args=[orcamento.pk])
        )
        self.assertContains(pagina, "ORC-000001")
        self.assertContains(pagina, "Calibração de manômetro")
        self.assertContains(pagina, "150")
        self.assertContains(pagina, "Rascunho")
        inexistente = self.client.get(reverse("servicos:imprimir_orcamento", args=[99999]))
        self.assertEqual(inexistente.status_code, 404)
        self.client.logout()
        anonimo = self.client.get(
            reverse("servicos:imprimir_orcamento", args=[orcamento.pk])
        )
        self.assertEqual(anonimo.status_code, 302)

    def test_os_antiga_sem_orcamento_continua(self):
        ordem = OrdemServico.criar(
            cliente=self.cliente_a,
            data_entrada=self.hoje,
        )
        self.assertIsNone(ordem.orcamento_id)
        detalhe = self.client.get(reverse("servicos:detalhe_ordem", args=[ordem.pk]))
        self.assertEqual(detalhe.status_code, 200)

    def _orcamento_aprovado(self):
        orcamento = Orcamento.criar(cliente=self.cliente_a, data_emissao=self.hoje)
        return orcamento

    def _gerar_os(self, orcamento):
        self.assertTrue(orcamento.alterar_status(StatusOrcamento.ENVIADO)[0])
        self.assertTrue(orcamento.alterar_status(StatusOrcamento.APROVADO)[0])
        return orcamento.gerar_ordem_servico()

    def test_orcamento_dois_manometros_gera_os(self):
        orcamento = self._orcamento_aprovado()
        self._item(orcamento, self.instrumento_a)
        self._item(
            orcamento,
            self.instrumento_a2,
            servico=ServicoSolicitado.CALIBRACAO,
            descricao="Calibração MAN-002",
            ordem=2,
        )
        ordem, erro = self._gerar_os(orcamento)
        self.assertFalse(erro)
        self.assertEqual(ordem.status, StatusOrdemServico.RECEBIDA)
        self.assertEqual(ordem.itens.count(), 2)
        self.assertEqual(
            set(ordem.itens.values_list("instrumento__codigo", flat=True)),
            {"MAN-001", "MAN-002"},
        )

    def test_orcamento_duas_valvulas_gera_os(self):
        orcamento = self._orcamento_aprovado()
        self._item(
            orcamento,
            None,
            valvula=self.valvula_a,
            servico=ServicoSolicitado.MANUTENCAO,
            descricao="Manutenção VAL-001",
        )
        self._item(
            orcamento,
            None,
            valvula=self.valvula_a2,
            servico=ServicoSolicitado.ENSAIO,
            descricao="Ensaio VAL-002",
            ordem=2,
        )
        ordem, erro = self._gerar_os(orcamento)
        self.assertFalse(erro)
        self.assertEqual(ordem.itens.count(), 2)
        itens = {item.codigo_equipamento: item for item in ordem.itens.all()}
        self.assertEqual(itens["VAL-001"].tipo_equipamento, TipoEquipamento.VALVULA)
        self.assertEqual(itens["VAL-001"].servico_solicitado, ServicoSolicitado.MANUTENCAO)
        self.assertEqual(itens["VAL-002"].servico_solicitado, ServicoSolicitado.ENSAIO)
        self.assertEqual(ordem.status, StatusOrdemServico.RECEBIDA)

    def test_orcamento_misto_gera_os_unica_sem_duplicar(self):
        self.cliente_a.contato_principal = "João da Silva"
        self.cliente_a.telefone = "(14) 99999-9999"
        self.cliente_a.email = "joao@empresa.com"
        self.cliente_a.save()
        orcamento = self._orcamento_aprovado()
        self._item(orcamento, self.instrumento_a)
        self._item(
            orcamento,
            self.instrumento_a2,
            descricao="Calibração MAN-002",
            ordem=2,
        )
        self._item(
            orcamento,
            None,
            valvula=self.valvula_a,
            servico=ServicoSolicitado.MANUTENCAO,
            descricao="Manutenção VAL-001",
            ordem=3,
        )
        self._item(
            orcamento,
            None,
            valvula=self.valvula_a2,
            servico=ServicoSolicitado.ENSAIO,
            descricao="Ensaio VAL-002",
            ordem=4,
        )
        ordem, erro = self._gerar_os(orcamento)
        self.assertFalse(erro)
        self.assertEqual(ordem.cliente_id, self.cliente_a.pk)
        self.assertEqual(ordem.status, StatusOrdemServico.RECEBIDA)
        self.assertEqual(ordem.itens.count(), 4)
        self.assertEqual(ordem.resumo_progresso()["percentual"], 0)
        self.assertEqual(ordem.solicitante, "João da Silva")
        self.assertEqual(ordem.telefone_solicitante, "(14) 99999-9999")
        self.assertEqual(ordem.email_solicitante, "joao@empresa.com")
        itens = {item.codigo_equipamento: item for item in ordem.itens.all()}
        self.assertEqual(itens["MAN-001"].tipo_equipamento, TipoEquipamento.INSTRUMENTO)
        self.assertEqual(itens["MAN-001"].servico_solicitado, ServicoSolicitado.CALIBRACAO)
        self.assertEqual(itens["VAL-001"].tipo_equipamento, TipoEquipamento.VALVULA)
        self.assertEqual(itens["VAL-002"].servico_solicitado, ServicoSolicitado.ENSAIO)
        itens["MAN-001"].aplicar_status(StatusItemOrdem.CONCLUIDO, sincronizar=False)
        self.assertEqual(ordem.resumo_progresso()["percentual"], 25)
        segunda, mensagem = orcamento.gerar_ordem_servico()
        self.assertEqual(segunda.pk, ordem.pk)
        self.assertIn("já gerada", mensagem.lower())
        self.assertEqual(OrdemServico.objects.count(), 1)
        detalhe = self.client.get(reverse("servicos:detalhe_orcamento", args=[orcamento.pk]))
        self.assertContains(detalhe, "Ver OS")
        self.assertNotContains(detalhe, "Gerar OS")

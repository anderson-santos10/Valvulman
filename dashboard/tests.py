from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from clientes.models import Cliente
from dashboard.paineis import montar_paineis
from servicos.models import (
    Cobranca,
    Orcamento,
    OrdemServico,
    StatusOrcamento,
    StatusOrdemServico,
)


class AutenticacaoTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="operador",
            email="operador@example.com",
            password="senha-segura-123",
        )
        self.urls_protegidas = [
            reverse("home"),
            reverse("clientes:lista_clientes"),
            reverse("clientes:cadastrar_cliente"),
            reverse("servicos:relatorio_tecnico"),
            reverse("servicos:ordens_servico"),
            reverse("servicos:lista_relatorios"),
            reverse("servicos:certificados"),
            reverse("servicos:lista_valvulas"),
            reverse("servicos:cadastrar_valvula"),
            reverse("servicos:lista_instrumentos"),
            reverse("servicos:cadastrar_instrumento"),
            reverse("servicos:lista_padroes"),
            reverse("servicos:cadastrar_padrao"),
            reverse("servicos:lista_ordens"),
            reverse("servicos:cadastrar_ordem"),
            reverse("servicos:fila_ordens"),
            reverse("servicos:lista_orcamentos"),
            reverse("servicos:cadastrar_orcamento"),
            reverse("servicos:lista_cobrancas"),
            reverse("servicos:cadastrar_cobranca"),
            reverse("acesso:lista_usuarios"),
            reverse("design_system"),
            reverse("configuracoes"),
            reverse("servicos:lista_calibracoes"),
            reverse("servicos:cadastrar_calibracao"),
            reverse("servicos:lista_certificados"),
        ]

    def test_usuario_nao_autenticado_nao_acessa_areas_protegidas(self):
        for url in self.urls_protegidas:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("login"), response.url)

    def test_login_permanece_publico(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)

    def test_login_preserva_parametro_next(self):
        response = self.client.get(reverse("login"), {"next": "/clientes/"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="next"')
        self.assertContains(response, 'value="/clientes/"')

    def test_usuario_autenticado_acessa_areas_protegidas(self):
        self.client.login(username="operador", password="senha-segura-123")
        for url in self.urls_protegidas:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

    def test_logout_redireciona_para_login(self):
        self.client.login(username="operador", password="senha-segura-123")
        response = self.client.post(reverse("logout"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("login"))
        follow = self.client.get(reverse("home"))
        self.assertEqual(follow.status_code, 302)

    def test_design_system_exige_staff(self):
        comum = User.objects.create_user("consulta", "consulta@example.com", "senha-segura-123")
        self.client.login(username="consulta", password="senha-segura-123")
        response = self.client.get(reverse("design_system"))
        self.assertEqual(response.status_code, 403)
        self.client.logout()
        self.client.login(username="operador", password="senha-segura-123")
        catalogo = self.client.get(reverse("design_system"))
        self.assertEqual(catalogo.status_code, 200)
        self.assertContains(catalogo, "Fundação visual Valvulman")


class DashboardInteligenteTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="operador",
            email="operador@example.com",
            password="senha-segura-123",
        )
        self.client.login(username="operador", password="senha-segura-123")
        self.hoje = timezone.localdate()
        self.cliente = Cliente.objects.create(
            nome="Empresa Dashboard",
            cnpj="11.222.333/0001-81",
            cep="17512-400",
            endereco="Rua Industrial, 10",
        )

    def test_dashboard_vazio_nao_mostra_cards_zerados_nem_graficos(self):
        home = self.client.get(reverse("home"))
        self.assertEqual(home.status_code, 200)
        self.assertFalse(home.context["paineis"]["tem_movimento_visivel"])
        self.assertContains(home, "Ainda não existem movimentações registradas.")
        self.assertNotContains(home, "OS por situação")
        self.assertNotContains(home, "OS atrasadas")
        self.assertNotContains(home, 'data-chart="os"')
        self.assertNotContains(home, 'data-chart="calibracoes"')
        self.assertNotContains(home, 'data-chart="comercial"')
        self.assertNotContains(home, 'data-chart="financeiro"')

    def test_paineis_ocultam_zeros_e_destacam_excecoes(self):
        paineis = montar_paineis(
            {
                "os_abertas": 0,
                "os_em_execucao": 3,
                "os_aguardando_revisao": 0,
                "os_prontas_entrega": 0,
                "os_entregues": 0,
                "os_atrasadas": 4,
                "calibracoes_concluidas": 0,
                "calibracoes_aprovadas": 0,
                "calibracoes_reprovadas": 0,
                "instrumentos_vencidos": 2,
                "orcamentos_rascunho": 0,
                "orcamentos_enviados": 0,
                "orcamentos_aprovados": 0,
                "orcamentos_vencidos": 1,
                "valor_negociacao": Decimal("0.00"),
                "contas_a_receber": Decimal("0.00"),
                "cobrancas_vencidas": Decimal("120.00"),
                "cobrancas_a_vencer": Decimal("0.00"),
                "recebido_mes": Decimal("0.00"),
                "qtd_cobrancas_vencidas": 1,
            }
        )
        rotulos_os = [item["rotulo"] for item in paineis["operacao"]["series"]]
        self.assertEqual(rotulos_os, ["Em execução", "Atrasadas"])
        self.assertEqual(paineis["operacao"]["alertas"][0]["valor"], 4)
        self.assertTrue(paineis["calibracoes"]["tem_dados"])
        self.assertEqual(paineis["calibracoes"]["alertas"][0]["valor"], 2)
        self.assertEqual(paineis["comercial"]["alertas"][0]["valor"], 1)
        self.assertTrue(paineis["financeiro"]["series"][0]["alerta"])

    def test_dashboard_com_os_renderiza_grafico_e_alerta(self):
        OrdemServico.criar(
            cliente=self.cliente,
            data_entrada=self.hoje,
            status=StatusOrdemServico.EM_EXECUCAO,
        )
        OrdemServico.criar(
            cliente=self.cliente,
            data_entrada=self.hoje,
            data_previsao_entrega=self.hoje - timedelta(days=1),
            status=StatusOrdemServico.ABERTA,
        )
        home = self.client.get(reverse("home"))
        self.assertContains(home, 'data-chart="os"')
        self.assertContains(home, "Em execução")
        self.assertContains(home, "OS atrasadas")
        self.assertContains(home, "Abertas")
        self.assertNotContains(home, "Aguardando revisão")

    def test_dashboard_orcamento_e_cobranca_vencidos(self):
        orcamento = Orcamento.criar(
            cliente=self.cliente,
            data_emissao=self.hoje - timedelta(days=10),
            data_validade=self.hoje - timedelta(days=1),
        )
        Orcamento.objects.filter(pk=orcamento.pk).update(
            status=StatusOrcamento.ENVIADO
        )
        Cobranca.criar(
            cliente=self.cliente,
            descricao="Cobrança dashboard",
            valor_original=Decimal("200.00"),
            data_emissao=self.hoje,
            data_vencimento=self.hoje - timedelta(days=2),
        )
        home = self.client.get(reverse("home"))
        self.assertContains(home, "Orçamentos vencidos")
        self.assertContains(home, "Cobranças vencidas")
        self.assertContains(home, 'data-chart="financeiro"')
        self.assertContains(home, 'data-chart="comercial"')

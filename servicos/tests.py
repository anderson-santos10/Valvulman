from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from clientes.models import Cliente

from .models import RelatorioTecnico, ValvulaRelatorio


class RelatorioECertificadoTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="operador",
            email="operador@example.com",
            password="senha-segura-123",
        )
        self.client.login(username="operador", password="senha-segura-123")
        self.cliente = Cliente.objects.create(
            nome="Indústria Alpha",
            cnpj="11.222.333/0001-81",
            cep="17512-400",
            endereco="Rua Industrial, 10",
        )

    def test_relatorio_tecnico_pode_ser_criado_com_valvulas(self):
        response = self.client.post(
            reverse("servicos:relatorio_tecnico"),
            {
                "cliente": self.cliente.pk,
                "numero_relatorio": "RAT-001",
                "folha": "01",
                "setor": "Utilidades",
                "valvula_item[]": ["1"],
                "valvula_serie[]": ["SN-100"],
                "valvula_tag[]": ["PSV-01"],
                "valvula_diametro[]": ["1 pol"],
                "valvula_modelo[]": ["M1"],
                "valvula_fabricante[]": ["Valvulman"],
                "valvula_pressao[]": ["150"],
                "valvula_servico[]": ["D"],
                "valvula_observacao[]": ["Calibrar"],
            },
        )
        self.assertEqual(response.status_code, 302)
        relatorio = RelatorioTecnico.objects.get(numero_relatorio="RAT-001")
        self.assertEqual(relatorio.cliente, self.cliente)
        valvula = ValvulaRelatorio.objects.get(relatorio=relatorio)
        self.assertEqual(valvula.numero_serie, "SN-100")
        self.assertEqual(valvula.tag, "PSV-01")
        self.assertRedirects(
            response,
            reverse("servicos:detalhe_relatorio", args=[relatorio.pk]),
        )

    def test_valvula_vazia_nao_e_salva(self):
        self.client.post(
            reverse("servicos:relatorio_tecnico"),
            {
                "cliente": self.cliente.pk,
                "numero_relatorio": "RAT-002",
                "folha": "01",
                "valvula_item[]": ["1"],
                "valvula_serie[]": ["   "],
                "valvula_tag[]": [""],
                "valvula_diametro[]": [""],
                "valvula_modelo[]": [""],
                "valvula_fabricante[]": [""],
                "valvula_pressao[]": [""],
                "valvula_servico[]": [""],
                "valvula_observacao[]": [""],
            },
        )
        relatorio = RelatorioTecnico.objects.get(numero_relatorio="RAT-002")
        self.assertEqual(relatorio.valvulas.count(), 0)

    def test_certificado_existente_abre_sem_quebrar(self):
        relatorio = RelatorioTecnico.objects.create(
            cliente=self.cliente,
            numero_relatorio="RAT-003",
            setor="Caldeiras",
        )
        ValvulaRelatorio.objects.create(
            relatorio=relatorio,
            item=1,
            numero_serie="SN-200",
            tag="PSV-02",
        )
        response = self.client.get(
            reverse("servicos:certificado_calibracao", args=[relatorio.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CERTIFICADO DE CALIBRAÇÃO")
        self.assertContains(response, "Indústria Alpha")
        self.assertContains(response, "PSV-02")

    def test_relatorio_sem_cliente_exibe_erro(self):
        response = self.client.post(
            reverse("servicos:relatorio_tecnico"),
            {
                "folha": "01",
                "numero_relatorio": "RAT-004",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Não foi possível salvar o relatório")
        self.assertFalse(RelatorioTecnico.objects.filter(numero_relatorio="RAT-004").exists())

    def _criar_relatorio(self, numero="RAT-010"):
        relatorio = RelatorioTecnico.objects.create(
            cliente=self.cliente,
            numero_relatorio=numero,
            setor="Caldeiras",
            observacoes="Observação inicial",
        )
        ValvulaRelatorio.objects.create(
            relatorio=relatorio,
            item=1,
            numero_serie="SN-200",
            tag="PSV-02",
        )
        return relatorio

    def test_listagem_autenticado_acessa(self):
        relatorio = self._criar_relatorio()
        for url_name in ("ordens_servico", "lista_relatorios"):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(f"servicos:{url_name}"))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, relatorio.numero_relatorio)
                self.assertContains(response, "Visualizar")
                self.assertContains(response, "Editar")
                self.assertContains(response, "Imprimir")

    def test_detalhe_autenticado_visualiza_relatorio(self):
        relatorio = self._criar_relatorio()
        response = self.client.get(
            reverse("servicos:detalhe_relatorio", args=[relatorio.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Indústria Alpha")
        self.assertContains(response, "11.222.333/0001-81")
        self.assertContains(response, "PSV-02")
        self.assertContains(response, "Observação inicial")

    def test_edicao_atualiza_sem_criar_outro_relatorio(self):
        relatorio = self._criar_relatorio()
        response = self.client.post(
            reverse("servicos:editar_relatorio", args=[relatorio.pk]),
            {
                "cliente": self.cliente.pk,
                "numero_relatorio": "RAT-010-EDIT",
                "folha": "02",
                "setor": "Utilidades",
                "observacoes": "Observação atualizada",
                "valvula_item[]": ["1"],
                "valvula_serie[]": ["SN-200"],
                "valvula_tag[]": ["PSV-02"],
                "valvula_diametro[]": [""],
                "valvula_modelo[]": [""],
                "valvula_fabricante[]": [""],
                "valvula_pressao[]": [""],
                "valvula_servico[]": [""],
                "valvula_observacao[]": [""],
            },
        )
        self.assertRedirects(
            response,
            reverse("servicos:detalhe_relatorio", args=[relatorio.pk]),
        )
        self.assertEqual(RelatorioTecnico.objects.count(), 1)
        relatorio.refresh_from_db()
        self.assertEqual(relatorio.numero_relatorio, "RAT-010-EDIT")
        self.assertEqual(relatorio.setor, "Utilidades")
        self.assertEqual(relatorio.observacoes, "Observação atualizada")
        self.assertEqual(relatorio.valvulas.count(), 1)
        self.assertEqual(relatorio.valvulas.get().tag, "PSV-02")

    def test_edicao_preserva_relacionamento_de_valvulas(self):
        relatorio = self._criar_relatorio()
        self.client.post(
            reverse("servicos:editar_relatorio", args=[relatorio.pk]),
            {
                "cliente": self.cliente.pk,
                "numero_relatorio": "RAT-010",
                "folha": "01",
                "setor": "Caldeiras",
                "valvula_item[]": ["1", "2"],
                "valvula_serie[]": ["SN-200", "SN-300"],
                "valvula_tag[]": ["PSV-02", "PSV-03"],
                "valvula_diametro[]": ["", ""],
                "valvula_modelo[]": ["", ""],
                "valvula_fabricante[]": ["", ""],
                "valvula_pressao[]": ["", ""],
                "valvula_servico[]": ["", ""],
                "valvula_observacao[]": ["", ""],
            },
        )
        self.assertEqual(RelatorioTecnico.objects.count(), 1)
        tags = list(
            relatorio.valvulas.order_by("item").values_list("tag", flat=True)
        )
        self.assertEqual(tags, ["PSV-02", "PSV-03"])

    def test_rotas_de_relatorio_exigem_login(self):
        relatorio = self._criar_relatorio()
        self.client.logout()
        urls = [
            reverse("servicos:ordens_servico"),
            reverse("servicos:lista_relatorios"),
            reverse("servicos:detalhe_relatorio", args=[relatorio.pk]),
            reverse("servicos:editar_relatorio", args=[relatorio.pk]),
            reverse("servicos:imprimir_relatorio", args=[relatorio.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("login"), response.url)

    def test_relatorio_inexistente_retorna_404(self):
        for url_name in (
            "detalhe_relatorio",
            "editar_relatorio",
            "imprimir_relatorio",
            "certificado_calibracao",
        ):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(f"servicos:{url_name}", args=[99999]))
                self.assertEqual(response.status_code, 404)

    def test_edicao_invalida_nao_salva_e_preserva_dados(self):
        relatorio = self._criar_relatorio()
        response = self.client.post(
            reverse("servicos:editar_relatorio", args=[relatorio.pk]),
            {
                "numero_relatorio": "RAT-010",
                "folha": "01",
                "setor": "Novo setor",
                "valvula_item[]": ["1"],
                "valvula_serie[]": ["SN-999"],
                "valvula_tag[]": ["PSV-99"],
                "valvula_diametro[]": [""],
                "valvula_modelo[]": [""],
                "valvula_fabricante[]": [""],
                "valvula_pressao[]": [""],
                "valvula_servico[]": [""],
                "valvula_observacao[]": [""],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Não foi possível salvar o relatório")
        self.assertContains(response, "SN-999")
        relatorio.refresh_from_db()
        self.assertEqual(relatorio.setor, "Caldeiras")
        self.assertEqual(relatorio.valvulas.count(), 1)
        self.assertEqual(relatorio.valvulas.get().tag, "PSV-02")

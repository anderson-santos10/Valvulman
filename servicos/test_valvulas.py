from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from clientes.models import Cliente

from .models import RelatorioTecnico, UnidadePressao, Valvula, ValvulaRelatorio


class ValvulaCadastroTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="operador",
            email="operador@example.com",
            password="senha-segura-123",
        )
        self.client.login(username="operador", password="senha-segura-123")
        self.cliente_a = Cliente.objects.create(
            nome="Indústria Alpha",
            cnpj="11.222.333/0001-81",
            cep="17512-400",
            endereco="Rua Industrial, 10",
        )
        self.cliente_b = Cliente.objects.create(
            nome="Indústria Beta",
            cnpj="11.444.777/0001-61",
            cep="17512-400",
            endereco="Rua Comercial, 20",
        )

    def _criar_valvula(self, cliente=None, codigo="PSV-001"):
        return Valvula.objects.create(
            cliente=cliente or self.cliente_a,
            codigo=codigo,
            tag="PSV-01",
            numero_serie="SN-100",
            fabricante="Valvulman",
            modelo="M1",
            diametro_nominal='1"',
            pressao_ajuste="150.000",
            unidade_pressao=UnidadePressao.PSI,
        )

    def test_valvula_pode_ser_criada_e_pertence_ao_cliente(self):
        valvula = self._criar_valvula()
        self.assertEqual(valvula.cliente, self.cliente_a)
        self.assertEqual(valvula.codigo, "PSV-001")
        self.assertTrue(valvula.ativo)
        self.assertEqual(str(valvula), "PSV-001 — PSV-01")
        self.assertEqual(valvula.pressao_formatada, "150 psi")

    def test_codigo_e_unico_por_cliente(self):
        self._criar_valvula(codigo="PSV-001")
        self._criar_valvula(cliente=self.cliente_b, codigo="PSV-001")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Valvula.objects.create(
                    cliente=self.cliente_a,
                    codigo="PSV-001",
                )

    def test_inativacao_altera_status(self):
        valvula = self._criar_valvula()
        response = self.client.post(
            reverse("servicos:inativar_valvula", args=[valvula.pk])
        )
        self.assertRedirects(
            response,
            reverse("servicos:detalhe_valvula", args=[valvula.pk]),
        )
        valvula.refresh_from_db()
        self.assertFalse(valvula.ativo)
        self.assertTrue(Valvula.objects.filter(pk=valvula.pk).exists())

    def test_crud_autenticado(self):
        valvula = self._criar_valvula()
        self.assertEqual(self.client.get(reverse("servicos:lista_valvulas")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("servicos:cadastrar_valvula")).status_code,
            200,
        )
        detalhe = self.client.get(reverse("servicos:detalhe_valvula", args=[valvula.pk]))
        self.assertEqual(detalhe.status_code, 200)
        self.assertContains(detalhe, "PSV-001")
        self.assertContains(detalhe, "Indústria Alpha")

        edicao = self.client.post(
            reverse("servicos:editar_valvula", args=[valvula.pk]),
            {
                "cliente": self.cliente_a.pk,
                "codigo": "PSV-001",
                "tag": "PSV-01A",
                "numero_serie": "SN-100",
                "fabricante": "Valvulman",
                "modelo": "M2",
                "diametro_nominal": '1"',
                "pressao_ajuste": "160",
                "unidade_pressao": UnidadePressao.BAR,
                "observacoes": "",
                "ativo": "on",
            },
        )
        self.assertRedirects(
            edicao,
            reverse("servicos:detalhe_valvula", args=[valvula.pk]),
        )
        valvula.refresh_from_db()
        self.assertEqual(valvula.tag, "PSV-01A")
        self.assertEqual(valvula.modelo, "M2")
        self.assertEqual(valvula.unidade_pressao, UnidadePressao.BAR)

    def test_cadastro_web_cria_valvula(self):
        response = self.client.post(
            reverse("servicos:cadastrar_valvula"),
            {
                "cliente": self.cliente_a.pk,
                "codigo": "PSV-010",
                "tag": "PSV-10",
                "unidade_pressao": UnidadePressao.PSI,
                "ativo": "on",
            },
        )
        valvula = Valvula.objects.get(codigo="PSV-010")
        self.assertRedirects(
            response,
            reverse("servicos:detalhe_valvula", args=[valvula.pk]),
        )
        self.assertEqual(valvula.cliente, self.cliente_a)

    def test_nao_autenticado_e_redirecionado(self):
        valvula = self._criar_valvula()
        self.client.logout()
        urls = [
            reverse("servicos:lista_valvulas"),
            reverse("servicos:cadastrar_valvula"),
            reverse("servicos:detalhe_valvula", args=[valvula.pk]),
            reverse("servicos:editar_valvula", args=[valvula.pk]),
            reverse("servicos:valvulas_por_cliente", args=[self.cliente_a.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("login"), response.url)

    def test_valvula_inexistente_retorna_404(self):
        for name in ("detalhe_valvula", "editar_valvula"):
            with self.subTest(name=name):
                response = self.client.get(reverse(f"servicos:{name}", args=[99999]))
                self.assertEqual(response.status_code, 404)

    def test_json_lista_apenas_valvulas_ativas_do_cliente(self):
        propria = self._criar_valvula(codigo="PSV-001")
        self._criar_valvula(cliente=self.cliente_b, codigo="PSV-002")
        inativa = self._criar_valvula(codigo="PSV-003")
        inativa.ativo = False
        inativa.save(update_fields=["ativo"])

        response = self.client.get(
            reverse("servicos:valvulas_por_cliente", args=[self.cliente_a.pk])
        )
        self.assertEqual(response.status_code, 200)
        ids = [item["id"] for item in response.json()["valvulas"]]
        self.assertEqual(ids, [propria.pk])

    def test_relatorio_nao_aceita_valvula_de_outro_cliente(self):
        valvula_b = self._criar_valvula(cliente=self.cliente_b, codigo="PSV-099")
        response = self.client.post(
            reverse("servicos:relatorio_tecnico"),
            {
                "cliente": self.cliente_a.pk,
                "numero_relatorio": "RAT-VALV",
                "folha": "01",
                "valvula_item[]": ["1"],
                "valvula_serie[]": ["SN-X"],
                "valvula_tag[]": ["PSV-X"],
                "valvula_diametro[]": [""],
                "valvula_modelo[]": [""],
                "valvula_fabricante[]": [""],
                "valvula_pressao[]": [""],
                "valvula_servico[]": [""],
                "valvula_observacao[]": [""],
                "valvula_cadastro[]": [str(valvula_b.pk)],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Não é permitido vincular uma válvula de outro cliente",
        )
        self.assertFalse(
            RelatorioTecnico.objects.filter(numero_relatorio="RAT-VALV").exists()
        )

    def test_relatorio_pode_vincular_valvula_do_mesmo_cliente(self):
        valvula = self._criar_valvula()
        response = self.client.post(
            reverse("servicos:relatorio_tecnico"),
            {
                "cliente": self.cliente_a.pk,
                "numero_relatorio": "RAT-OK",
                "folha": "01",
                "valvula_item[]": ["1"],
                "valvula_serie[]": [valvula.numero_serie],
                "valvula_tag[]": [valvula.tag],
                "valvula_diametro[]": [valvula.diametro_nominal],
                "valvula_modelo[]": [valvula.modelo],
                "valvula_fabricante[]": [valvula.fabricante],
                "valvula_pressao[]": [valvula.pressao_formatada],
                "valvula_servico[]": ["D"],
                "valvula_observacao[]": [""],
                "valvula_cadastro[]": [str(valvula.pk)],
            },
        )
        relatorio = RelatorioTecnico.objects.get(numero_relatorio="RAT-OK")
        self.assertRedirects(
            response,
            reverse("servicos:detalhe_relatorio", args=[relatorio.pk]),
        )
        item = relatorio.valvulas.get()
        self.assertEqual(item.valvula, valvula)
        self.assertEqual(item.tag, "PSV-01")

    def test_relatorio_historico_sem_cadastro_continua_funcionando(self):
        relatorio = RelatorioTecnico.objects.create(
            cliente=self.cliente_a,
            numero_relatorio="RAT-OLD",
            setor="Caldeiras",
        )
        ValvulaRelatorio.objects.create(
            relatorio=relatorio,
            item=1,
            numero_serie="SN-LEGADO",
            tag="PSV-LEG",
        )
        response = self.client.get(
            reverse("servicos:detalhe_relatorio", args=[relatorio.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PSV-LEG")
        self.assertContains(response, "SN-LEGADO")
        item = relatorio.valvulas.get()
        self.assertIsNone(item.valvula_id)

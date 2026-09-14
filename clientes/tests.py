from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from servicos.models import Instrumento, RelatorioTecnico, TipoInstrumento, UnidadePressao, Valvula, ValvulaRelatorio

from .cnpj import format_cnpj, is_valid_cnpj
from .forms import ClienteForm
from .models import Cliente

CNPJ_VALIDO = "11.222.333/0001-81"
CNPJ_VALIDO_SEM_MASCARA = "11222333000181"


class ClienteCadastroTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="operador",
            email="operador@example.com",
            password="senha-segura-123",
        )
        self.client.login(username="operador", password="senha-segura-123")

    def test_cadastro_de_cliente_funciona(self):
        response = self.client.post(
            reverse("clientes:cadastrar_cliente"),
            {
                "nome": "Empresa Teste LTDA",
                "cnpj": CNPJ_VALIDO,
                "cep": "17512-400",
                "endereco": "Rua das Válvulas, 100",
            },
        )
        self.assertEqual(response.status_code, 302)
        cliente = Cliente.objects.get(nome="Empresa Teste LTDA")
        self.assertEqual(cliente.cnpj, CNPJ_VALIDO)
        self.assertRedirects(
            response,
            reverse("clientes:detalhe_cliente", args=[cliente.pk]),
        )

    def test_cnpj_sem_mascara_e_armazenado_formatado(self):
        form = ClienteForm(
            data={
                "nome": "Cliente Máscara",
                "cnpj": CNPJ_VALIDO_SEM_MASCARA,
                "cep": "17512-400",
                "endereco": "Rua A, 1",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        cliente = form.save()
        self.assertEqual(cliente.cnpj, format_cnpj(CNPJ_VALIDO_SEM_MASCARA))

    def test_cnpj_invalido_e_rejeitado(self):
        casos = [
            "123",
            "00.000.000/0000-00",
            "11.111.111/1111-11",
            "11.222.333/0001-00",
        ]
        for cnpj in casos:
            with self.subTest(cnpj=cnpj):
                form = ClienteForm(
                    data={
                        "nome": "Cliente Inválido",
                        "cnpj": cnpj,
                        "cep": "17512-400",
                        "endereco": "Rua B, 2",
                    }
                )
                self.assertFalse(form.is_valid())
                self.assertIn("cnpj", form.errors)

    def test_cnpj_valido_conhecido(self):
        self.assertTrue(is_valid_cnpj(CNPJ_VALIDO))
        self.assertFalse(is_valid_cnpj("11222333000100"))


class ClienteDetalheTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="operador",
            email="operador@example.com",
            password="senha-segura-123",
        )
        self.client.login(username="operador", password="senha-segura-123")
        self.cliente = Cliente.objects.create(
            nome="Indústria Alpha",
            cnpj=CNPJ_VALIDO,
            cep="17512-400",
            endereco="Rua Industrial, 10",
        )
        self.outro_cliente = Cliente.objects.create(
            nome="Indústria Beta",
            cnpj="11.444.777/0001-61",
            cep="17512-400",
            endereco="Rua Comercial, 20",
        )

    def test_autenticado_abre_detalhe(self):
        response = self.client.get(
            reverse("clientes:detalhe_cliente", args=[self.cliente.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Indústria Alpha")
        self.assertContains(response, CNPJ_VALIDO)
        self.assertContains(response, "17512-400")
        self.assertContains(response, "Rua Industrial, 10")
        self.assertContains(
            response,
            reverse("clientes:editar_cliente", args=[self.cliente.pk]),
        )
        self.assertContains(
            response,
            reverse("servicos:lista_valvulas") + f"?cliente={self.cliente.pk}",
        )
        self.assertContains(
            response,
            reverse("servicos:cadastrar_valvula") + f"?cliente={self.cliente.pk}",
        )
        self.assertContains(
            response,
            reverse("servicos:lista_instrumentos") + f"?cliente={self.cliente.pk}",
        )
        self.assertContains(
            response,
            reverse("servicos:cadastrar_instrumento") + f"?cliente={self.cliente.pk}",
        )

    def test_cliente_inexistente_retorna_404(self):
        response = self.client.get(reverse("clientes:detalhe_cliente", args=[99999]))
        self.assertEqual(response.status_code, 404)

    def test_nao_autenticado_e_redirecionado(self):
        self.client.logout()
        response = self.client.get(
            reverse("clientes:detalhe_cliente", args=[self.cliente.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_detalhe_mostra_valvulas_do_cliente_e_esconde_as_de_outro(self):
        ativa = Valvula.objects.create(
            cliente=self.cliente,
            codigo="PSV-001",
            tag="PSV-01",
            fabricante="Valvulman",
            modelo="M1",
            numero_serie="SN-100",
            ativo=True,
        )
        inativa = Valvula.objects.create(
            cliente=self.cliente,
            codigo="PSV-002",
            tag="PSV-02",
            fabricante="Outro",
            modelo="M2",
            numero_serie="SN-200",
            ativo=False,
        )
        alheia = Valvula.objects.create(
            cliente=self.outro_cliente,
            codigo="PSV-099",
            tag="PSV-99",
            numero_serie="SN-999",
        )
        response = self.client.get(
            reverse("clientes:detalhe_cliente", args=[self.cliente.pk])
        )
        self.assertContains(response, ativa.codigo)
        self.assertContains(response, inativa.codigo)
        self.assertContains(response, "Ativa")
        self.assertContains(response, "Inativa")
        self.assertNotContains(response, alheia.codigo)
        self.assertContains(response, reverse("servicos:detalhe_valvula", args=[ativa.pk]))

    def test_detalhe_mostra_instrumentos_do_cliente_e_esconde_os_de_outro(self):
        ativo = Instrumento.objects.create(
            cliente=self.cliente,
            codigo="MAN-001",
            tag="PI-01",
            fabricante="Wika",
            modelo="233.50",
            numero_serie="SN-I-100",
            tipo=TipoInstrumento.MANOMETRO,
            faixa_minima="0",
            faixa_maxima="10",
            unidade=UnidadePressao.BAR,
            ativo=True,
        )
        inativo = Instrumento.objects.create(
            cliente=self.cliente,
            codigo="MAN-002",
            tag="PI-02",
            fabricante="Ashcroft",
            modelo="1009",
            numero_serie="SN-I-200",
            ativo=False,
        )
        alheio = Instrumento.objects.create(
            cliente=self.outro_cliente,
            codigo="MAN-099",
            tag="PI-99",
            numero_serie="SN-I-999",
        )
        response = self.client.get(
            reverse("clientes:detalhe_cliente", args=[self.cliente.pk])
        )
        self.assertContains(response, ativo.codigo)
        self.assertContains(response, inativo.codigo)
        self.assertContains(response, "Ativo")
        self.assertContains(response, "Inativo")
        self.assertNotContains(response, alheio.codigo)
        self.assertContains(
            response,
            reverse("servicos:detalhe_instrumento", args=[ativo.pk]),
        )

    def test_detalhe_mostra_relatorios_do_cliente_e_esconde_os_de_outro(self):
        relatorio = RelatorioTecnico.objects.create(
            cliente=self.cliente,
            numero_relatorio="RAT-CLI",
        )
        ValvulaRelatorio.objects.create(
            relatorio=relatorio,
            item=1,
            tag="PSV-01",
        )
        alheio = RelatorioTecnico.objects.create(
            cliente=self.outro_cliente,
            numero_relatorio="RAT-OUTRO",
        )
        response = self.client.get(
            reverse("clientes:detalhe_cliente", args=[self.cliente.pk])
        )
        self.assertContains(response, "RAT-CLI")
        self.assertNotContains(response, "RAT-OUTRO")
        self.assertContains(
            response,
            reverse("servicos:detalhe_relatorio", args=[relatorio.pk]),
        )
        self.assertContains(
            response,
            reverse("servicos:editar_relatorio", args=[relatorio.pk]),
        )
        self.assertContains(
            response,
            reverse("servicos:imprimir_relatorio", args=[relatorio.pk]),
        )
        self.assertNotContains(
            response,
            reverse("servicos:detalhe_relatorio", args=[alheio.pk]),
        )

    def test_lista_de_clientes_aponta_para_detalhe(self):
        response = self.client.get(reverse("clientes:lista_clientes"))
        self.assertContains(
            response,
            reverse("clientes:detalhe_cliente", args=[self.cliente.pk]),
        )


class ClienteContatoTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="operador",
            email="operador@example.com",
            password="senha-segura-123",
        )
        self.client.login(username="operador", password="senha-segura-123")

    def test_cliente_sem_contato(self):
        cliente = Cliente.objects.create(
            nome="Sem Contato",
            cnpj=CNPJ_VALIDO,
            cep="17512-400",
            endereco="Rua A, 1",
        )
        self.assertEqual(cliente.contato_principal, "")
        self.assertEqual(cliente.telefone, "")
        self.assertEqual(cliente.email, "")
        detalhe = self.client.get(reverse("clientes:detalhe_cliente", args=[cliente.pk]))
        self.assertContains(detalhe, "Telefone")
        self.assertContains(detalhe, "E-mail")

    def test_cliente_com_telefone(self):
        cliente = Cliente.objects.create(
            nome="Com Telefone",
            cnpj="11.444.777/0001-61",
            cep="17512-400",
            endereco="Rua B, 2",
            telefone="(14) 99999-1111",
        )
        self.assertEqual(cliente.telefone, "(14) 99999-1111")
        self.assertEqual(cliente.email, "")

    def test_cliente_com_email(self):
        cliente = Cliente.objects.create(
            nome="Com Email",
            cnpj="11.444.777/0001-61",
            cep="17512-400",
            endereco="Rua C, 3",
            email="contato@empresa.com",
        )
        self.assertEqual(cliente.email, "contato@empresa.com")

    def test_cliente_com_telefone_e_email(self):
        response = self.client.post(
            reverse("clientes:cadastrar_cliente"),
            {
                "nome": "Metalúrgica Alfa Ltda.",
                "cnpj": CNPJ_VALIDO,
                "cep": "17512-400",
                "endereco": "Rua Industrial, 10",
                "contato_principal": "João da Silva",
                "telefone": "(14) 99999-9999",
                "email": "joao@empresa.com",
            },
        )
        cliente = Cliente.objects.get(nome="Metalúrgica Alfa Ltda.")
        self.assertRedirects(
            response, reverse("clientes:detalhe_cliente", args=[cliente.pk])
        )
        self.assertEqual(cliente.contato_principal, "João da Silva")
        self.assertEqual(cliente.telefone, "(14) 99999-9999")
        self.assertEqual(cliente.email, "joao@empresa.com")
        detalhe = self.client.get(reverse("clientes:detalhe_cliente", args=[cliente.pk]))
        self.assertContains(detalhe, "João da Silva")
        self.assertContains(detalhe, "(14) 99999-9999")
        self.assertContains(detalhe, "joao@empresa.com")

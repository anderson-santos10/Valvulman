from decimal import Decimal

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from clientes.models import Cliente

from .models import Instrumento, TipoInstrumento, UnidadePressao


class InstrumentoCadastroTests(TestCase):
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

    def _criar_instrumento(self, cliente=None, codigo="MAN-001", **extra):
        dados = {
            "cliente": cliente or self.cliente_a,
            "codigo": codigo,
            "tag": "PI-01",
            "numero_serie": "SN-I-100",
            "tipo": TipoInstrumento.MANOMETRO,
            "fabricante": "Wika",
            "modelo": "233.50",
            "faixa_minima": "0.000",
            "faixa_maxima": "10.000",
            "unidade": UnidadePressao.BAR,
            "resolucao": "0.100",
        }
        dados.update(extra)
        return Instrumento.objects.create(**dados)

    def test_instrumento_pode_ser_criado_e_pertence_ao_cliente(self):
        instrumento = self._criar_instrumento()
        self.assertEqual(instrumento.cliente, self.cliente_a)
        self.assertEqual(instrumento.codigo, "MAN-001")
        self.assertEqual(instrumento.tipo, TipoInstrumento.MANOMETRO)
        self.assertTrue(instrumento.ativo)
        self.assertEqual(str(instrumento), "MAN-001 — PI-01")
        self.assertEqual(instrumento.faixa_formatada, "0 a 10 bar")
        self.assertEqual(instrumento.resolucao_formatada, "0.1 bar")
        self.assertEqual(Instrumento._formatar_decimal(Decimal("10")), "10")
        self.assertEqual(Instrumento._formatar_decimal(Decimal("0")), "0")
        self.assertEqual(Instrumento._formatar_decimal(Decimal("0.100")), "0.1")

    def test_codigo_e_unico_por_cliente(self):
        self._criar_instrumento(codigo="MAN-001")
        self._criar_instrumento(cliente=self.cliente_b, codigo="MAN-001")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Instrumento.objects.create(
                    cliente=self.cliente_a,
                    codigo="MAN-001",
                )

    def test_faixa_minima_nao_pode_ser_maior_que_maxima(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Instrumento.objects.create(
                    cliente=self.cliente_a,
                    codigo="MAN-ERR",
                    faixa_minima="20",
                    faixa_maxima="10",
                    unidade=UnidadePressao.BAR,
                )

    def test_inativacao_altera_status(self):
        instrumento = self._criar_instrumento()
        response = self.client.post(
            reverse("servicos:inativar_instrumento", args=[instrumento.pk])
        )
        self.assertRedirects(
            response,
            reverse("servicos:detalhe_instrumento", args=[instrumento.pk]),
        )
        instrumento.refresh_from_db()
        self.assertFalse(instrumento.ativo)
        self.assertTrue(Instrumento.objects.filter(pk=instrumento.pk).exists())

    def test_crud_autenticado(self):
        instrumento = self._criar_instrumento()
        self.assertEqual(
            self.client.get(reverse("servicos:lista_instrumentos")).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("servicos:cadastrar_instrumento")).status_code,
            200,
        )
        detalhe = self.client.get(
            reverse("servicos:detalhe_instrumento", args=[instrumento.pk])
        )
        self.assertEqual(detalhe.status_code, 200)
        self.assertContains(detalhe, "MAN-001")
        self.assertContains(detalhe, "Indústria Alpha")
        self.assertContains(detalhe, "Manômetro")
        self.assertContains(detalhe, "0 a 10 bar")
        self.assertContains(detalhe, "Histórico de calibrações")

        edicao = self.client.post(
            reverse("servicos:editar_instrumento", args=[instrumento.pk]),
            {
                "cliente": self.cliente_a.pk,
                "codigo": "MAN-001",
                "tag": "PI-01A",
                "numero_serie": "SN-I-100",
                "tipo": TipoInstrumento.MANOMETRO,
                "fabricante": "Wika",
                "modelo": "233.51",
                "faixa_minima": "0",
                "faixa_maxima": "16",
                "unidade": UnidadePressao.BAR,
                "resolucao": "0.2",
                "observacoes": "",
                "ativo": "on",
            },
        )
        self.assertRedirects(
            edicao,
            reverse("servicos:detalhe_instrumento", args=[instrumento.pk]),
        )
        instrumento.refresh_from_db()
        self.assertEqual(instrumento.tag, "PI-01A")
        self.assertEqual(instrumento.modelo, "233.51")
        self.assertEqual(str(instrumento.faixa_maxima), "16.000")

    def test_cadastro_web_cria_instrumento(self):
        response = self.client.post(
            reverse("servicos:cadastrar_instrumento"),
            {
                "cliente": self.cliente_a.pk,
                "codigo": "MAN-010",
                "tag": "PI-10",
                "tipo": TipoInstrumento.MANOMETRO,
                "unidade": UnidadePressao.PSI,
                "ativo": "on",
            },
        )
        instrumento = Instrumento.objects.get(codigo="MAN-010")
        self.assertRedirects(
            response,
            reverse("servicos:detalhe_instrumento", args=[instrumento.pk]),
        )
        self.assertEqual(instrumento.cliente, self.cliente_a)

    def test_preenche_cliente_pelo_parametro_get(self):
        response = self.client.get(
            reverse("servicos:cadastrar_instrumento"),
            {"cliente": self.cliente_a.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            str(response.context["form"].initial.get("cliente")),
            str(self.cliente_a.pk),
        )

    def test_parametro_cliente_inexistente_nao_associa(self):
        response = self.client.get(
            reverse("servicos:cadastrar_instrumento"),
            {"cliente": "99999"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["form"].initial.get("cliente"))

    def test_parametro_cliente_nao_substitui_cliente_enviado_no_post(self):
        response = self.client.post(
            reverse("servicos:cadastrar_instrumento")
            + f"?cliente={self.cliente_b.pk}",
            {
                "cliente": self.cliente_a.pk,
                "codigo": "MAN-POST",
                "tipo": TipoInstrumento.MANOMETRO,
                "unidade": UnidadePressao.PSI,
                "ativo": "on",
            },
        )
        instrumento = Instrumento.objects.get(codigo="MAN-POST")
        self.assertRedirects(
            response,
            reverse("servicos:detalhe_instrumento", args=[instrumento.pk]),
        )
        self.assertEqual(instrumento.cliente, self.cliente_a)

    def test_edicao_nao_troca_o_cliente_proprietario(self):
        instrumento = self._criar_instrumento()
        response = self.client.post(
            reverse("servicos:editar_instrumento", args=[instrumento.pk]),
            {
                "cliente": self.cliente_b.pk,
                "codigo": "MAN-001",
                "tag": "PI-01",
                "numero_serie": "SN-I-100",
                "tipo": TipoInstrumento.MANOMETRO,
                "fabricante": "Wika",
                "modelo": "233.50",
                "faixa_minima": "0",
                "faixa_maxima": "10",
                "unidade": UnidadePressao.BAR,
                "resolucao": "0.1",
                "observacoes": "",
                "ativo": "on",
            },
        )
        self.assertRedirects(
            response,
            reverse("servicos:detalhe_instrumento", args=[instrumento.pk]),
        )
        instrumento.refresh_from_db()
        self.assertEqual(instrumento.cliente, self.cliente_a)

    def test_formulario_rejeita_faixa_invalida(self):
        response = self.client.post(
            reverse("servicos:cadastrar_instrumento"),
            {
                "cliente": self.cliente_a.pk,
                "codigo": "MAN-FAIXA",
                "tipo": TipoInstrumento.MANOMETRO,
                "faixa_minima": "20",
                "faixa_maxima": "10",
                "unidade": UnidadePressao.BAR,
                "ativo": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "O limite inferior da faixa não pode ser maior que o limite superior.",
        )
        self.assertFalse(Instrumento.objects.filter(codigo="MAN-FAIXA").exists())

    def test_nao_autenticado_e_redirecionado(self):
        instrumento = self._criar_instrumento()
        self.client.logout()
        urls = [
            reverse("servicos:lista_instrumentos"),
            reverse("servicos:cadastrar_instrumento"),
            reverse("servicos:detalhe_instrumento", args=[instrumento.pk]),
            reverse("servicos:editar_instrumento", args=[instrumento.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("login"), response.url)
        inativar = self.client.post(
            reverse("servicos:inativar_instrumento", args=[instrumento.pk])
        )
        self.assertEqual(inativar.status_code, 302)
        self.assertIn(reverse("login"), inativar.url)
        instrumento.refresh_from_db()
        self.assertTrue(instrumento.ativo)

    def test_instrumento_inexistente_retorna_404(self):
        for name in ("detalhe_instrumento", "editar_instrumento"):
            with self.subTest(name=name):
                response = self.client.get(reverse(f"servicos:{name}", args=[99999]))
                self.assertEqual(response.status_code, 404)
        response = self.client.post(
            reverse("servicos:inativar_instrumento", args=[99999])
        )
        self.assertEqual(response.status_code, 404)

    def test_listagem_filtra_por_cliente_tipo_e_status(self):
        proprio = self._criar_instrumento(codigo="MAN-001")
        inativo = self._criar_instrumento(codigo="MAN-002")
        inativo.ativo = False
        inativo.save(update_fields=["ativo"])
        outro = self._criar_instrumento(cliente=self.cliente_b, codigo="MAN-099")

        lista_cliente = self.client.get(
            reverse("servicos:lista_instrumentos"),
            {"cliente": self.cliente_a.pk},
        )
        self.assertContains(lista_cliente, proprio.codigo)
        self.assertContains(lista_cliente, inativo.codigo)
        self.assertNotContains(lista_cliente, outro.codigo)

        lista_ativos = self.client.get(
            reverse("servicos:lista_instrumentos"),
            {"cliente": self.cliente_a.pk, "status": "ativo"},
        )
        self.assertContains(lista_ativos, proprio.codigo)
        self.assertNotContains(lista_ativos, inativo.codigo)

        lista_tipo = self.client.get(
            reverse("servicos:lista_instrumentos"),
            {"tipo": TipoInstrumento.MANOMETRO},
        )
        self.assertContains(lista_tipo, proprio.codigo)
        self.assertContains(lista_tipo, outro.codigo)

from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from clientes.models import Cliente

from .models import (
    Calibracao,
    Instrumento,
    PadraoMedicao,
    PontoCalibracao,
    ResultadoCalibracao,
    StatusCalibracao,
    TipoInstrumento,
    UnidadePressao,
)


def preparar_conclusao(calibracao, user):
    calibracao.registrar_execucao(user)
    calibracao.registrar_revisao(user)
    calibracao.save()
    return calibracao


class CalibracaoCicloTests(TestCase):
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
        self.instrumento_a = Instrumento.objects.create(
            cliente=self.cliente_a,
            codigo="MAN-001",
            tag="PI-01",
            numero_serie="SN-I-100",
            tipo=TipoInstrumento.MANOMETRO,
            fabricante="Wika",
            faixa_minima="0",
            faixa_maxima="10",
            unidade=UnidadePressao.BAR,
        )
        self.instrumento_b = Instrumento.objects.create(
            cliente=self.cliente_b,
            codigo="MAN-099",
            tag="PI-99",
            numero_serie="SN-I-999",
            faixa_minima="0",
            faixa_maxima="16",
            unidade=UnidadePressao.BAR,
        )
        self.padrao = PadraoMedicao.objects.create(
            codigo="PAD-0001",
            identificacao="Calibrador de pressão digital",
            fabricante="Fluke",
            modelo="729",
            numero_serie="FL729",
            data_validade=date(2027, 12, 31),
        )

    def _dados_formset(self, pontos, inicial=0):
        dados = {
            "pontos-TOTAL_FORMS": str(len(pontos)),
            "pontos-INITIAL_FORMS": str(inicial),
            "pontos-MIN_NUM_FORMS": "0",
            "pontos-MAX_NUM_FORMS": "1000",
        }
        for indice, ponto in enumerate(pontos):
            prefixo = f"pontos-{indice}"
            dados[f"{prefixo}-ordem"] = str(ponto["ordem"])
            dados[f"{prefixo}-valor_referencia"] = str(ponto["valor_referencia"])
            dados[f"{prefixo}-indicacao_instrumento"] = str(
                ponto["indicacao_instrumento"]
            )
            dados[f"{prefixo}-observacoes"] = ponto.get("observacoes", "")
            if ponto.get("id"):
                dados[f"{prefixo}-id"] = str(ponto["id"])
            if ponto.get("DELETE"):
                dados[f"{prefixo}-DELETE"] = "on"
        return dados

    def _criar_calibracao(self, instrumento=None, numero=None, **extra):
        dados = {
            "instrumento": instrumento or self.instrumento_a,
            "data_calibracao": date(2026, 9, 10),
            "procedimento": "PROC-CAL-001",
            "padrao_utilizado": "Fluke 729",
            "status": StatusCalibracao.RASCUNHO,
            "resultado": ResultadoCalibracao.PENDENTE,
        }
        dados.update(extra)
        if numero:
            dados["numero"] = numero
        return Calibracao.objects.create(**dados)

    def test_calibracao_pertence_ao_instrumento_e_gera_numero(self):
        primeira = self._criar_calibracao()
        segunda = self._criar_calibracao()
        self.assertEqual(primeira.instrumento, self.instrumento_a)
        self.assertEqual(primeira.numero, "CAL-0001")
        self.assertEqual(segunda.numero, "CAL-0002")
        self.assertEqual(self.instrumento_a.calibracoes.count(), 2)

    def test_numero_e_unico_por_instrumento(self):
        self._criar_calibracao(numero="CAL-LAB-1")
        self._criar_calibracao(instrumento=self.instrumento_b, numero="CAL-LAB-1")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Calibracao.objects.create(
                    instrumento=self.instrumento_a,
                    numero="CAL-LAB-1",
                    data_calibracao=date(2026, 9, 11),
                )

    def test_erro_e_calculado_com_decimal(self):
        calibracao = self._criar_calibracao()
        ponto = PontoCalibracao.objects.create(
            calibracao=calibracao,
            ordem=1,
            valor_referencia="10.000",
            indicacao_instrumento="10.100",
        )
        self.assertEqual(ponto.erro, Decimal("0.100"))
        self.assertEqual(ponto.erro_formatado, "+0.1 bar")
        self.assertEqual(
            PontoCalibracao.calcular_erro(Decimal("9.9"), Decimal("10")),
            Decimal("-0.1"),
        )

    def test_ordem_unica_na_calibracao(self):
        calibracao = self._criar_calibracao()
        PontoCalibracao.objects.create(
            calibracao=calibracao,
            ordem=1,
            valor_referencia="0",
            indicacao_instrumento="0",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PontoCalibracao.objects.create(
                    calibracao=calibracao,
                    ordem=1,
                    valor_referencia="2",
                    indicacao_instrumento="2",
                )

    def test_crud_web_cria_pontos_e_aparece_no_historico(self):
        dados = {
            "instrumento": self.instrumento_a.pk,
            "numero": "",
            "data_calibracao": "2026-09-10",
            "procedimento": "PROC-CAL-001",
            "padrao": self.padrao.pk,
            "status": StatusCalibracao.CONCLUIDA,
            "resultado": ResultadoCalibracao.APROVADO,
            "observacoes": "Ensaio inicial",
        }
        dados.update(
            self._dados_formset(
                [
                    {"ordem": 1, "valor_referencia": "0", "indicacao_instrumento": "0.0"},
                    {"ordem": 2, "valor_referencia": "10", "indicacao_instrumento": "10.1"},
                ]
            )
        )
        response = self.client.post(reverse("servicos:cadastrar_calibracao"), dados)
        calibracao = Calibracao.objects.get(instrumento=self.instrumento_a)
        self.assertRedirects(
            response,
            reverse("servicos:detalhe_calibracao", args=[calibracao.pk]),
        )
        self.assertEqual(calibracao.numero, "CAL-0001")
        self.assertEqual(calibracao.pontos.count(), 2)
        self.assertEqual(calibracao.pontos.get(ordem=2).erro, Decimal("0.100"))

        detalhe = self.client.get(
            reverse("servicos:detalhe_calibracao", args=[calibracao.pk])
        )
        self.assertContains(detalhe, "CAL-0001")
        self.assertContains(detalhe, "PAD-0001")
        self.assertContains(detalhe, "Fluke")
        self.assertContains(detalhe, "+0.1 bar")

        historico = self.client.get(
            reverse("servicos:detalhe_instrumento", args=[self.instrumento_a.pk])
        )
        self.assertContains(historico, "CAL-0001")
        self.assertContains(
            historico,
            reverse("servicos:cadastrar_calibracao")
            + f"?instrumento={self.instrumento_a.pk}",
        )

        lista = self.client.get(reverse("servicos:lista_calibracoes"))
        self.assertContains(lista, "CAL-0001")
        self.assertContains(lista, "Indústria Alpha")

    def test_edicao_remove_ponto_e_preserva_instrumento(self):
        calibracao = self._criar_calibracao()
        ponto_um = PontoCalibracao.objects.create(
            calibracao=calibracao,
            ordem=1,
            valor_referencia="0",
            indicacao_instrumento="0",
        )
        ponto_dois = PontoCalibracao.objects.create(
            calibracao=calibracao,
            ordem=2,
            valor_referencia="4",
            indicacao_instrumento="4.1",
        )
        dados = {
            "cliente": self.cliente_b.pk,
            "instrumento": self.instrumento_b.pk,
            "numero": calibracao.numero,
            "data_calibracao": "2026-09-12",
            "procedimento": "IT-07",
            "padrao_utilizado": "Fluke 729",
            "status": StatusCalibracao.RASCUNHO,
            "resultado": ResultadoCalibracao.PENDENTE,
            "observacoes": "",
        }
        dados.update(
            self._dados_formset(
                [
                    {
                        "id": ponto_um.pk,
                        "ordem": 1,
                        "valor_referencia": "0",
                        "indicacao_instrumento": "0.2",
                    },
                    {
                        "id": ponto_dois.pk,
                        "ordem": 2,
                        "valor_referencia": "4",
                        "indicacao_instrumento": "4.1",
                        "DELETE": True,
                    },
                ],
                inicial=2,
            )
        )
        response = self.client.post(
            reverse("servicos:editar_calibracao", args=[calibracao.pk]),
            dados,
        )
        self.assertRedirects(
            response,
            reverse("servicos:detalhe_calibracao", args=[calibracao.pk]),
        )
        calibracao.refresh_from_db()
        self.assertEqual(calibracao.instrumento, self.instrumento_a)
        self.assertEqual(calibracao.procedimento, "IT-07")
        self.assertEqual(calibracao.pontos.count(), 1)
        self.assertEqual(calibracao.pontos.get().indicacao_instrumento, Decimal("0.200"))

    def test_referencia_fora_da_faixa_e_rejeitada_e_preserva_dados(self):
        dados = {
            "instrumento": self.instrumento_a.pk,
            "data_calibracao": "2026-09-10",
            "status": StatusCalibracao.RASCUNHO,
            "resultado": ResultadoCalibracao.PENDENTE,
        }
        dados.update(
            self._dados_formset(
                [
                    {
                        "ordem": 1,
                        "valor_referencia": "15",
                        "indicacao_instrumento": "15",
                    }
                ]
            )
        )
        response = self.client.post(reverse("servicos:cadastrar_calibracao"), dados)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "acima da faixa do instrumento")
        self.assertContains(response, 'value="15"')
        self.assertFalse(Calibracao.objects.exists())

    def test_parametro_instrumento_preenche_e_id_inexistente_nao_associa(self):
        response = self.client.get(
            reverse("servicos:cadastrar_calibracao"),
            {"instrumento": self.instrumento_a.pk},
        )
        self.assertEqual(
            str(response.context["form"].initial.get("instrumento")),
            str(self.instrumento_a.pk),
        )
        invalido = self.client.get(
            reverse("servicos:cadastrar_calibracao"),
            {"instrumento": "99999"},
        )
        self.assertFalse(invalido.context["form"].initial.get("instrumento"))

    def test_parametro_get_nao_substitui_instrumento_do_post(self):
        dados = {
            "instrumento": self.instrumento_a.pk,
            "data_calibracao": "2026-09-10",
            "status": StatusCalibracao.RASCUNHO,
            "resultado": ResultadoCalibracao.PENDENTE,
        }
        dados.update(self._dados_formset([]))
        response = self.client.post(
            reverse("servicos:cadastrar_calibracao")
            + f"?instrumento={self.instrumento_b.pk}",
            dados,
        )
        calibracao = Calibracao.objects.get()
        self.assertRedirects(
            response,
            reverse("servicos:detalhe_calibracao", args=[calibracao.pk]),
        )
        self.assertEqual(calibracao.instrumento, self.instrumento_a)

    def test_cancelamento_preserva_registro(self):
        calibracao = self._criar_calibracao()
        response = self.client.post(
            reverse("servicos:cancelar_calibracao", args=[calibracao.pk])
        )
        self.assertRedirects(
            response,
            reverse("servicos:detalhe_calibracao", args=[calibracao.pk]),
        )
        calibracao.refresh_from_db()
        self.assertEqual(calibracao.status, StatusCalibracao.CANCELADA)
        self.assertTrue(Calibracao.objects.filter(pk=calibracao.pk).exists())
        edicao = self.client.get(
            reverse("servicos:editar_calibracao", args=[calibracao.pk])
        )
        self.assertRedirects(
            edicao,
            reverse("servicos:detalhe_calibracao", args=[calibracao.pk]),
        )

    def test_nao_autenticado_e_redirecionado(self):
        calibracao = self._criar_calibracao()
        self.client.logout()
        urls = [
            reverse("servicos:lista_calibracoes"),
            reverse("servicos:cadastrar_calibracao"),
            reverse("servicos:detalhe_calibracao", args=[calibracao.pk]),
            reverse("servicos:editar_calibracao", args=[calibracao.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("login"), response.url)

    def test_inexistente_retorna_404(self):
        for name in ("detalhe_calibracao", "editar_calibracao"):
            with self.subTest(name=name):
                response = self.client.get(reverse(f"servicos:{name}", args=[99999]))
                self.assertEqual(response.status_code, 404)
        response = self.client.post(
            reverse("servicos:cancelar_calibracao", args=[99999])
        )
        self.assertEqual(response.status_code, 404)

    def test_cliente_mostra_quantidade_de_calibracoes_do_proprio_instrumento(self):
        self._criar_calibracao()
        self._criar_calibracao(instrumento=self.instrumento_b, numero="CAL-OUTRO")
        response = self.client.get(
            reverse("clientes:detalhe_cliente", args=[self.cliente_a.pk])
        )
        self.assertContains(response, self.instrumento_a.codigo)
        self.assertNotContains(response, self.instrumento_b.codigo)
        self.assertEqual(
            response.context["instrumentos_ativos"][0].total_calibracoes,
            1,
        )


class CalibracaoAceitacaoTests(TestCase):
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
        self.instrumento = Instrumento.objects.create(
            cliente=self.cliente_a,
            codigo="MAN-001",
            tag="PI-01",
            tipo=TipoInstrumento.MANOMETRO,
            faixa_minima=Decimal("0"),
            faixa_maxima=Decimal("10"),
            unidade=UnidadePressao.BAR,
        )
        self.instrumento_sem_faixa = Instrumento.objects.create(
            cliente=self.cliente_a,
            codigo="MAN-002",
            unidade=UnidadePressao.BAR,
        )
        self.instrumento_b = Instrumento.objects.create(
            cliente=self.cliente_b,
            codigo="MAN-099",
            unidade=UnidadePressao.PSI,
        )

    def _formset(self, pontos, inicial=0):
        dados = {
            "pontos-TOTAL_FORMS": str(len(pontos)),
            "pontos-INITIAL_FORMS": str(inicial),
            "pontos-MIN_NUM_FORMS": "0",
            "pontos-MAX_NUM_FORMS": "1000",
        }
        for indice, ponto in enumerate(pontos):
            prefixo = f"pontos-{indice}"
            dados[f"{prefixo}-ordem"] = str(ponto["ordem"])
            dados[f"{prefixo}-valor_referencia"] = str(ponto["valor_referencia"])
            dados[f"{prefixo}-indicacao_instrumento"] = str(
                ponto["indicacao_instrumento"]
            )
            dados[f"{prefixo}-observacoes"] = ""
        return dados

    def _criar_rascunho(self, tolerancia="0.10", **extra):
        dados = {
            "instrumento": self.instrumento,
            "data_calibracao": date(2026, 9, 10),
            "criterio_aceitacao": "Critério interno do cliente",
            "tolerancia": Decimal(tolerancia) if tolerancia is not None else None,
            "status": StatusCalibracao.RASCUNHO,
            "resultado": ResultadoCalibracao.PENDENTE,
        }
        dados.update(extra)
        return Calibracao.objects.create(**dados)

    def _ponto(self, calibracao, ordem, referencia, indicacao):
        return PontoCalibracao.objects.create(
            calibracao=calibracao,
            ordem=ordem,
            valor_referencia=Decimal(referencia),
            indicacao_instrumento=Decimal(indicacao),
        )

    def test_tolerancia_positiva_e_zero_sao_aceitas(self):
        positiva = self._criar_rascunho(tolerancia="0.10")
        zero = self._criar_rascunho(tolerancia="0")
        self.assertEqual(positiva.tolerancia, Decimal("0.10"))
        self.assertEqual(zero.tolerancia, Decimal("0"))
        self.assertEqual(positiva.tolerancia_formatada, "±0.1 bar")

    def test_tolerancia_negativa_e_rejeitada(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._criar_rascunho(tolerancia="-0.10")
        response = self.client.post(
            reverse("servicos:cadastrar_calibracao"),
            {
                "instrumento": self.instrumento.pk,
                "data_calibracao": "2026-09-10",
                "criterio_aceitacao": "Critério interno",
                "tolerancia": "-0.10",
                **self._formset([]),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A tolerância não pode ser negativa.")
        self.assertFalse(Calibracao.objects.exists())

    def test_resultado_do_ponto_usa_valor_absoluto(self):
        calibracao = self._criar_rascunho(tolerancia="0.10")
        menor = self._ponto(calibracao, 1, "10.00", "10.08")
        igual = self._ponto(calibracao, 2, "10.00", "10.10")
        maior = self._ponto(calibracao, 3, "10.00", "10.12")
        negativo_dentro = self._ponto(calibracao, 4, "10.00", "9.90")
        negativo_fora = self._ponto(calibracao, 5, "10.00", "9.80")
        self.assertEqual(menor.erro, Decimal("0.080"))
        self.assertEqual(igual.erro, Decimal("0.100"))
        self.assertEqual(maior.erro, Decimal("0.120"))
        self.assertEqual(negativo_dentro.erro, Decimal("-0.100"))
        self.assertEqual(negativo_fora.erro, Decimal("-0.200"))
        self.assertTrue(menor.dentro_da_tolerancia)
        self.assertTrue(igual.dentro_da_tolerancia)
        self.assertFalse(maior.dentro_da_tolerancia)
        self.assertTrue(negativo_dentro.dentro_da_tolerancia)
        self.assertFalse(negativo_fora.dentro_da_tolerancia)

    def test_precisao_decimal_no_limite(self):
        calibracao = self._criar_rascunho(tolerancia="0.05")
        ponto = self._ponto(calibracao, 1, "10.000", "10.049")
        self.assertEqual(ponto.erro, Decimal("0.049"))
        self.assertTrue(ponto.dentro_da_tolerancia)

    def test_rascunho_permanece_pendente(self):
        calibracao = self._criar_rascunho()
        self._ponto(calibracao, 1, "0", "0")
        calibracao.aplicar_resultado_oficial()
        self.assertEqual(calibracao.resultado, ResultadoCalibracao.PENDENTE)
        self.assertEqual(calibracao.calcular_resultado(), ResultadoCalibracao.PENDENTE)

    def test_conclusao_aprovada_e_reprovada(self):
        aprovada = self._criar_rascunho()
        self._ponto(aprovada, 1, "0", "0.05")
        self._ponto(aprovada, 2, "10", "10.10")
        preparar_conclusao(aprovada, self.user)
        self.client.post(reverse("servicos:concluir_calibracao", args=[aprovada.pk]))
        aprovada.refresh_from_db()
        self.assertEqual(aprovada.status, StatusCalibracao.CONCLUIDA)
        self.assertEqual(aprovada.resultado, ResultadoCalibracao.APROVADO)

        reprovada = self._criar_rascunho()
        self._ponto(reprovada, 1, "0", "0.05")
        self._ponto(reprovada, 2, "10", "10.20")
        preparar_conclusao(reprovada, self.user)
        self.client.post(reverse("servicos:concluir_calibracao", args=[reprovada.pk]))
        reprovada.refresh_from_db()
        self.assertEqual(reprovada.resultado, ResultadoCalibracao.REPROVADO)

    def test_post_nao_forca_resultado_aprovado(self):
        dados = {
            "instrumento": self.instrumento.pk,
            "data_calibracao": "2026-09-10",
            "criterio_aceitacao": "Critério interno do cliente",
            "tolerancia": "0.10",
            "status": StatusCalibracao.CONCLUIDA,
            "resultado": ResultadoCalibracao.APROVADO,
        }
        dados.update(
            self._formset(
                [{"ordem": 1, "valor_referencia": "10", "indicacao_instrumento": "10.50"}]
            )
        )
        self.client.post(reverse("servicos:cadastrar_calibracao"), dados)
        calibracao = Calibracao.objects.get()
        self.assertEqual(calibracao.status, StatusCalibracao.RASCUNHO)
        self.assertEqual(calibracao.resultado, ResultadoCalibracao.PENDENTE)
        preparar_conclusao(calibracao, self.user)
        self.client.post(reverse("servicos:concluir_calibracao", args=[calibracao.pk]))
        calibracao.refresh_from_db()
        self.assertEqual(calibracao.resultado, ResultadoCalibracao.REPROVADO)

    def test_concluir_exige_criterio_tolerancia_e_ponto(self):
        calibracao = Calibracao.objects.create(
            instrumento=self.instrumento,
            data_calibracao=date(2026, 9, 10),
        )
        response = self.client.post(
            reverse("servicos:concluir_calibracao", args=[calibracao.pk])
        )
        self.assertRedirects(
            response,
            reverse("servicos:editar_calibracao", args=[calibracao.pk]),
        )
        calibracao.refresh_from_db()
        self.assertEqual(calibracao.status, StatusCalibracao.RASCUNHO)

    def test_concluida_nao_edita_sem_reabrir(self):
        calibracao = self._criar_rascunho()
        self._ponto(calibracao, 1, "0", "0")
        preparar_conclusao(calibracao, self.user)
        self.client.post(reverse("servicos:concluir_calibracao", args=[calibracao.pk]))
        edicao = self.client.get(
            reverse("servicos:editar_calibracao", args=[calibracao.pk])
        )
        self.assertRedirects(
            edicao,
            reverse("servicos:detalhe_calibracao", args=[calibracao.pk]),
        )
        self.client.post(reverse("servicos:reabrir_calibracao", args=[calibracao.pk]))
        calibracao.refresh_from_db()
        self.assertEqual(calibracao.status, StatusCalibracao.RASCUNHO)
        self.assertEqual(calibracao.resultado, ResultadoCalibracao.PENDENTE)
        self.assertEqual(
            self.client.get(
                reverse("servicos:editar_calibracao", args=[calibracao.pk])
            ).status_code,
            200,
        )

    def test_cancelada_nao_e_resultado_valido(self):
        calibracao = self._criar_rascunho()
        self._ponto(calibracao, 1, "0", "0")
        preparar_conclusao(calibracao, self.user)
        self.client.post(reverse("servicos:concluir_calibracao", args=[calibracao.pk]))
        self.client.post(reverse("servicos:cancelar_calibracao", args=[calibracao.pk]))
        calibracao.refresh_from_db()
        self.assertEqual(calibracao.status, StatusCalibracao.CANCELADA)
        self.assertEqual(calibracao.resultado, ResultadoCalibracao.PENDENTE)
        self.assertFalse(calibracao.pode_editar)

    def test_faixa_minimo_e_maximo_sao_permitidos(self):
        dados = {
            "instrumento": self.instrumento.pk,
            "data_calibracao": "2026-09-10",
            "criterio_aceitacao": "Critério interno do cliente",
            "tolerancia": "0.10",
        }
        dados.update(
            self._formset(
                [
                    {"ordem": 1, "valor_referencia": "0", "indicacao_instrumento": "0"},
                    {"ordem": 2, "valor_referencia": "10", "indicacao_instrumento": "10"},
                ]
            )
        )
        response = self.client.post(reverse("servicos:cadastrar_calibracao"), dados)
        self.assertEqual(Calibracao.objects.count(), 1)
        self.assertRedirects(
            response,
            reverse(
                "servicos:detalhe_calibracao",
                args=[Calibracao.objects.get().pk],
            ),
        )

    def test_faixa_abaixo_e_acima_sao_rejeitadas(self):
        for valor in ("-0.001", "10.001"):
            with self.subTest(valor=valor):
                dados = {
                    "instrumento": self.instrumento.pk,
                    "data_calibracao": "2026-09-10",
                    **self._formset(
                        [
                            {
                                "ordem": 1,
                                "valor_referencia": valor,
                                "indicacao_instrumento": valor,
                            }
                        ]
                    ),
                }
                response = self.client.post(
                    reverse("servicos:cadastrar_calibracao"), dados
                )
                self.assertEqual(response.status_code, 200)
                self.assertFalse(Calibracao.objects.exists())

    def test_instrumento_sem_faixa_nao_quebra(self):
        dados = {
            "instrumento": self.instrumento_sem_faixa.pk,
            "data_calibracao": "2026-09-10",
            "criterio_aceitacao": "Especificação do fabricante",
            "tolerancia": "0.20",
        }
        dados.update(
            self._formset(
                [{"ordem": 1, "valor_referencia": "11", "indicacao_instrumento": "11"}]
            )
        )
        response = self.client.post(reverse("servicos:cadastrar_calibracao"), dados)
        calibracao = Calibracao.objects.get()
        self.assertRedirects(
            response,
            reverse("servicos:detalhe_calibracao", args=[calibracao.pk]),
        )
        self.assertEqual(calibracao.pontos.get().valor_referencia, Decimal("11.000"))

    def test_edicao_nao_troca_instrumento_mesmo_com_criterio(self):
        calibracao = self._criar_rascunho()
        ponto = self._ponto(calibracao, 1, "2", "2")
        dados = {
            "instrumento": self.instrumento_b.pk,
            "numero": calibracao.numero,
            "data_calibracao": "2026-09-11",
            "criterio_aceitacao": "Procedimento PROC-CAL-001",
            "tolerancia": "0.10",
        }
        dados.update(
            self._formset(
                [
                    {
                        "ordem": 1,
                        "valor_referencia": "2",
                        "indicacao_instrumento": "2",
                    }
                ],
                inicial=1,
            )
        )
        dados["pontos-0-id"] = str(ponto.pk)
        self.client.post(
            reverse("servicos:editar_calibracao", args=[calibracao.pk]),
            dados,
        )
        calibracao.refresh_from_db()
        self.assertEqual(calibracao.instrumento, self.instrumento)
        self.assertEqual(calibracao.criterio_aceitacao, "Procedimento PROC-CAL-001")

    def test_ensaio_completo_aprovado_e_reprovado(self):
        pontos_ok = [
            (1, "0", "0.02"),
            (2, "2", "2.05"),
            (3, "4", "4.00"),
            (4, "6", "5.95"),
            (5, "8", "8.10"),
            (6, "10", "10.10"),
        ]
        calibracao = self._criar_rascunho(tolerancia="0.10")
        for ordem, referencia, indicacao in pontos_ok:
            self._ponto(calibracao, ordem, referencia, indicacao)
        preparar_conclusao(calibracao, self.user)
        self.client.post(reverse("servicos:concluir_calibracao", args=[calibracao.pk]))
        calibracao.refresh_from_db()
        resumo = calibracao.resumo_aceitacao()
        self.assertEqual(calibracao.resultado, ResultadoCalibracao.APROVADO)
        self.assertEqual(resumo["avaliados"], 6)
        self.assertEqual(resumo["aprovados"], 6)
        self.assertEqual(resumo["reprovados"], 0)
        self.assertEqual(resumo["maior_erro_absoluto"], Decimal("0.100"))

        detalhe = self.client.get(
            reverse("servicos:detalhe_calibracao", args=[calibracao.pk])
        )
        self.assertContains(detalhe, "Critério interno do cliente")
        self.assertContains(detalhe, "±0.1 bar")
        self.assertContains(detalhe, "Aprovado")

        historico = self.client.get(
            reverse("servicos:detalhe_instrumento", args=[self.instrumento.pk])
        )
        self.assertContains(historico, "±0.1 bar")

        calibracao_reprovada = self._criar_rascunho(tolerancia="0.10")
        for ordem, referencia, indicacao in pontos_ok:
            self._ponto(calibracao_reprovada, ordem, referencia, indicacao)
        self._ponto(calibracao_reprovada, 7, "10", "10.15")
        preparar_conclusao(calibracao_reprovada, self.user)
        self.client.post(
            reverse("servicos:concluir_calibracao", args=[calibracao_reprovada.pk])
        )
        calibracao_reprovada.refresh_from_db()
        resumo_reprovado = calibracao_reprovada.resumo_aceitacao()
        self.assertEqual(calibracao_reprovada.resultado, ResultadoCalibracao.REPROVADO)
        self.assertEqual(resumo_reprovado["reprovados"], 1)
        self.assertEqual(resumo_reprovado["maior_erro_absoluto"], Decimal("0.150"))

    def test_conclusao_exige_revisao(self):
        calibracao = self._criar_rascunho()
        self._ponto(calibracao, 1, "0", "0")
        self.client.post(reverse("servicos:concluir_calibracao", args=[calibracao.pk]))
        calibracao.refresh_from_db()
        self.assertEqual(calibracao.status, StatusCalibracao.RASCUNHO)

    def test_revisao_e_snapshot_historico(self):
        self.user.first_name = "Maria"
        self.user.last_name = "Silva"
        self.user.save(update_fields=["first_name", "last_name"])
        calibracao = self._criar_rascunho()
        self._ponto(calibracao, 1, "0", "0")
        get_revisao = self.client.get(
            reverse("servicos:revisar_calibracao", args=[calibracao.pk])
        )
        self.assertEqual(get_revisao.status_code, 405)
        self.client.post(reverse("servicos:revisar_calibracao", args=[calibracao.pk]))
        calibracao.refresh_from_db()
        self.assertEqual(calibracao.executor_nome, "Maria Silva")
        self.assertEqual(calibracao.revisor_nome, "Maria Silva")
        self.assertTrue(calibracao.esta_revisada)
        self.user.first_name = "Outro"
        self.user.save(update_fields=["first_name"])
        calibracao.refresh_from_db()
        self.assertEqual(calibracao.executor_nome, "Maria Silva")
        self.assertEqual(calibracao.revisor_nome, "Maria Silva")
        self.client.post(reverse("servicos:concluir_calibracao", args=[calibracao.pk]))
        calibracao.refresh_from_db()
        self.assertEqual(calibracao.status, StatusCalibracao.CONCLUIDA)

    def test_edicao_limpa_revisao(self):
        calibracao = self._criar_rascunho()
        ponto = self._ponto(calibracao, 1, "0", "0")
        self.client.post(reverse("servicos:revisar_calibracao", args=[calibracao.pk]))
        calibracao.refresh_from_db()
        self.assertTrue(calibracao.esta_revisada)
        dados = {
            "instrumento": self.instrumento.pk,
            "numero": calibracao.numero,
            "data_calibracao": "2026-09-10",
            "criterio_aceitacao": "Critério interno do cliente",
            "tolerancia": "0.10",
        }
        dados.update(
            self._formset(
                [
                    {
                        "ordem": 1,
                        "valor_referencia": "0",
                        "indicacao_instrumento": "0",
                        "id": ponto.pk,
                    }
                ],
                inicial=1,
            )
        )
        dados["pontos-0-id"] = str(ponto.pk)
        self.client.post(
            reverse("servicos:editar_calibracao", args=[calibracao.pk]),
            dados,
        )
        calibracao.refresh_from_db()
        self.assertFalse(calibracao.esta_revisada)
        self.assertEqual(calibracao.executor_nome, "operador")

    def test_revisao_exige_login(self):
        calibracao = self._criar_rascunho()
        self._ponto(calibracao, 1, "0", "0")
        self.client.logout()
        response = self.client.post(
            reverse("servicos:revisar_calibracao", args=[calibracao.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)
        calibracao.refresh_from_db()
        self.assertFalse(calibracao.esta_revisada)

    def test_intervalo_de_validade_calcula_meses_e_fim_de_mes(self):
        self.assertEqual(
            Calibracao.adicionar_meses(date(2026, 1, 31), 1),
            date(2026, 2, 28),
        )
        self.assertEqual(
            Calibracao.adicionar_meses(date(2024, 1, 31), 1),
            date(2024, 2, 29),
        )
        self.assertEqual(
            Calibracao.adicionar_meses(date(2026, 9, 9), 12),
            date(2027, 9, 9),
        )
        calibracao = self._criar_rascunho()
        self._ponto(calibracao, 1, "0", "0")
        calibracao.criterio_aceitacao = "Critério interno"
        calibracao.tolerancia = Decimal("0.10")
        calibracao.intervalo_validade_meses = 12
        calibracao.data_calibracao = date(2026, 9, 9)
        preparar_conclusao(calibracao, self.user)
        self.client.post(reverse("servicos:concluir_calibracao", args=[calibracao.pk]))
        calibracao.refresh_from_db()
        self.assertEqual(calibracao.data_validade, date(2027, 9, 9))
        self.assertEqual(calibracao.data_proxima_calibracao, date(2027, 9, 9))

    def test_intervalo_zero_e_rejeitado_no_formulario(self):
        dados = {
            "instrumento": self.instrumento.pk,
            "numero": "",
            "data_calibracao": "2026-09-10",
            "procedimento": "",
            "padrao_utilizado": "",
            "criterio_aceitacao": "Critério interno",
            "tolerancia": "0.10",
            "intervalo_validade_meses": "0",
            "observacoes": "",
        }
        dados.update(
            self._formset(
                [{"ordem": 1, "valor_referencia": "0", "indicacao_instrumento": "0"}]
            )
        )
        response = self.client.post(reverse("servicos:cadastrar_calibracao"), dados)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Calibracao.objects.filter(instrumento=self.instrumento).exists())


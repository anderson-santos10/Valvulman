from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from clientes.models import Cliente

from .models import (
    Calibracao,
    CertificadoCalibracao,
    Instrumento,
    PadraoMedicao,
    PontoCalibracao,
    ResultadoCalibracao,
    TipoInstrumento,
    UnidadePressao,
)
from .test_calibracoes import preparar_conclusao


class PadraoMedicaoCadastroTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="operador",
            email="operador@example.com",
            password="senha-segura-123",
        )
        self.client.login(username="operador", password="senha-segura-123")

    def test_login_obrigatorio(self):
        self.client.logout()
        response = self.client.get(reverse("servicos:lista_padroes"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_cria_e_gera_codigo(self):
        response = self.client.post(
            reverse("servicos:cadastrar_padrao"),
            {
                "identificacao": "Calibrador de pressão digital",
                "tipo": "Calibrador de pressão",
                "fabricante": "Fluke",
                "modelo": "725",
                "numero_serie": "FL72512345",
                "faixa_minima": "0",
                "faixa_maxima": "10",
                "unidade": UnidadePressao.BAR,
                "resolucao": "0.01",
                "numero_certificado": "CERT-PAD-2026-001",
                "data_calibracao": "2026-01-01",
                "data_validade": "2027-01-01",
                "observacoes": "",
            },
        )
        padrao = PadraoMedicao.objects.get()
        self.assertRedirects(
            response,
            reverse("servicos:detalhe_padrao", args=[padrao.pk]),
        )
        self.assertEqual(padrao.codigo, "PAD-0001")
        self.assertTrue(padrao.ativo)
        self.assertEqual(padrao.faixa_formatada, "0 a 10 bar")
        detalhe = self.client.get(reverse("servicos:detalhe_padrao", args=[padrao.pk]))
        self.assertContains(detalhe, "CERT-PAD-2026-001")
        lista = self.client.get(reverse("servicos:lista_padroes"))
        self.assertContains(lista, "PAD-0001")

    def test_codigo_unico(self):
        PadraoMedicao.objects.create(
            codigo="PAD-0001",
            identificacao="Primeiro",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PadraoMedicao.objects.create(
                    codigo="PAD-0001",
                    identificacao="Duplicado",
                )
        response = self.client.post(
            reverse("servicos:cadastrar_padrao"),
            {"codigo": "PAD-0001", "identificacao": "Outro"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PadraoMedicao.objects.count(), 1)

    def test_edicao_nao_troca_codigo(self):
        padrao = PadraoMedicao.objects.create(
            codigo="PAD-0001",
            identificacao="Original",
        )
        self.client.post(
            reverse("servicos:editar_padrao", args=[padrao.pk]),
            {
                "codigo": "PAD-0099",
                "identificacao": "Atualizado",
                "ativo": "on",
            },
        )
        padrao.refresh_from_db()
        self.assertEqual(padrao.codigo, "PAD-0001")
        self.assertEqual(padrao.identificacao, "Atualizado")

    def test_faixa_e_resolucao_invalidas(self):
        response = self.client.post(
            reverse("servicos:cadastrar_padrao"),
            {
                "identificacao": "Padrão",
                "faixa_minima": "10",
                "faixa_maxima": "1",
                "unidade": UnidadePressao.BAR,
                "resolucao": "-0.1",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(PadraoMedicao.objects.exists())

    def test_inativacao_preserva_cadastro(self):
        padrao = PadraoMedicao.objects.create(
            codigo="PAD-0001",
            identificacao="Calibrador",
        )
        get_inativar = self.client.get(
            reverse("servicos:inativar_padrao", args=[padrao.pk])
        )
        self.assertEqual(get_inativar.status_code, 405)
        self.client.post(reverse("servicos:inativar_padrao", args=[padrao.pk]))
        padrao.refresh_from_db()
        self.assertFalse(padrao.ativo)
        self.assertTrue(PadraoMedicao.objects.filter(pk=padrao.pk).exists())

    def test_sem_validade_nao_inventa_prazo(self):
        padrao = PadraoMedicao.objects.create(
            codigo="PAD-0002",
            identificacao="Sem prazo",
        )
        self.assertEqual(padrao.situacao_validade, "sem_validade")
        self.assertEqual(padrao.validar_uso(date(2026, 9, 9)), "")


class PadraoMedicaoCalibracaoTests(TestCase):
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
        self.instrumento = Instrumento.objects.create(
            cliente=self.cliente,
            codigo="MAN-001",
            tipo=TipoInstrumento.MANOMETRO,
            faixa_minima=Decimal("0"),
            faixa_maxima=Decimal("10"),
            unidade=UnidadePressao.BAR,
        )
        self.padrao = PadraoMedicao.objects.create(
            codigo="PAD-0001",
            identificacao="Calibrador de pressão digital",
            fabricante="Fluke",
            modelo="725",
            numero_serie="FL72512345",
            numero_certificado="CERT-PAD-2026-001",
            data_calibracao=date(2026, 1, 1),
            data_validade=date(2027, 1, 1),
            unidade=UnidadePressao.BAR,
        )

    def _formset(self, pontos):
        dados = {
            "pontos-TOTAL_FORMS": str(len(pontos)),
            "pontos-INITIAL_FORMS": "0",
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

    def test_associa_padrao_valido_e_gera_snapshot(self):
        dados = {
            "instrumento": self.instrumento.pk,
            "data_calibracao": "2026-09-09",
            "padrao": self.padrao.pk,
            "criterio_aceitacao": "Critério interno",
            "tolerancia": "0.10",
        }
        dados.update(
            self._formset(
                [{"ordem": 1, "valor_referencia": "1", "indicacao_instrumento": "1"}]
            )
        )
        self.client.post(reverse("servicos:cadastrar_calibracao"), dados)
        calibracao = Calibracao.objects.get()
        self.assertEqual(calibracao.padrao, self.padrao)
        self.assertIn("PAD-0001", calibracao.padrao_utilizado)
        self.assertIn("FL72512345", calibracao.padrao_utilizado)
        self.assertIn("CERT-PAD-2026-001", calibracao.padrao_utilizado)

    def test_rejeita_padrao_inexistente_inativo_e_vencido(self):
        inativo = PadraoMedicao.objects.create(
            codigo="PAD-0002",
            identificacao="Inativo",
            ativo=False,
            data_validade=date(2027, 1, 1),
        )
        vencido = PadraoMedicao.objects.create(
            codigo="PAD-0003",
            identificacao="Vencido",
            data_validade=date(2026, 1, 1),
        )
        for padrao_id in (99999, inativo.pk, vencido.pk):
            with self.subTest(padrao_id=padrao_id):
                dados = {
                    "instrumento": self.instrumento.pk,
                    "data_calibracao": "2026-09-09",
                    "padrao": str(padrao_id),
                    "criterio_aceitacao": "Critério interno",
                    "tolerancia": "0.10",
                }
                dados.update(
                    self._formset(
                        [
                            {
                                "ordem": 1,
                                "valor_referencia": "1",
                                "indicacao_instrumento": "1",
                            }
                        ]
                    )
                )
                response = self.client.post(
                    reverse("servicos:cadastrar_calibracao"),
                    dados,
                )
                self.assertEqual(response.status_code, 200)
        self.assertFalse(Calibracao.objects.exists())

    def test_historico_preserva_snapshot_apos_alteracao_e_inativacao(self):
        calibracao = Calibracao.objects.create(
            instrumento=self.instrumento,
            data_calibracao=date(2026, 9, 9),
            padrao=self.padrao,
            criterio_aceitacao="Critério interno",
            tolerancia=Decimal("0.10"),
        )
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
        numero = certificado.numero
        self.padrao.numero_serie = "67890"
        self.padrao.identificacao = "Outro equipamento"
        self.padrao.save()
        self.client.post(reverse("servicos:inativar_padrao", args=[self.padrao.pk]))
        calibracao.refresh_from_db()
        self.assertEqual(calibracao.padrao_id, self.padrao.pk)
        self.assertIn("FL72512345", calibracao.padrao_utilizado)
        self.assertNotIn("67890", calibracao.padrao_utilizado)
        detalhe = self.client.get(
            reverse("servicos:detalhe_calibracao", args=[calibracao.pk])
        )
        self.assertContains(detalhe, "FL72512345")
        self.assertEqual(calibracao.resultado, ResultadoCalibracao.APROVADO)
        html = self.client.get(
            reverse("servicos:detalhe_certificado", args=[certificado.pk])
        )
        self.assertContains(html, "PAD-0001")
        self.assertContains(html, "FL72512345")
        self.assertContains(html, "CERT-PAD-2026-001")
        self.assertNotContains(html, "67890")
        from servicos.pdf import _renderizar_html

        pdf_html = _renderizar_html(certificado)
        self.assertIn("FL72512345", pdf_html)
        pdf = self.client.get(
            reverse("servicos:gerar_pdf_certificado", args=[certificado.pk])
        )
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        certificado.refresh_from_db()
        self.assertEqual(certificado.numero, numero)
        self.client.logout()
        publico = self.client.get(
            reverse("validar_certificado", args=[certificado.token_validacao])
        )
        self.assertContains(publico, certificado.numero)
        self.assertNotContains(publico, "FL72512345")
        self.assertNotContains(publico, "CERT-PAD-2026-001")
        self.client.login(username="operador", password="senha-segura-123")
        nova = self.client.get(reverse("servicos:cadastrar_calibracao"))
        self.assertNotContains(nova, "PAD-0001")
        historico = self.client.get(
            reverse("servicos:detalhe_padrao", args=[self.padrao.pk])
        )
        self.assertContains(historico, calibracao.numero)
        self.assertContains(historico, certificado.numero)

    def test_padrao_vencido_hoje_era_valido_na_data_da_calibracao(self):
        padrao = PadraoMedicao.objects.create(
            codigo="PAD-0009",
            identificacao="Histórico",
            numero_serie="SN-HIST",
            data_validade=date(2026, 1, 15),
        )
        calibracao = Calibracao.objects.create(
            instrumento=self.instrumento,
            data_calibracao=date(2026, 1, 10),
            padrao=padrao,
            criterio_aceitacao="Critério interno",
            tolerancia=Decimal("0.10"),
        )
        self.assertIn("SN-HIST", calibracao.padrao_utilizado)
        self.assertEqual(padrao.vigencia_em(date(2026, 1, 10)), "vigente")
        self.assertEqual(padrao.vigencia_em(date(2026, 9, 9)), "vencido")
        detalhe = self.client.get(
            reverse("servicos:detalhe_calibracao", args=[calibracao.pk])
        )
        self.assertContains(detalhe, "SN-HIST")
        self.assertContains(detalhe, "PAD-0009")
        self.assertEqual(padrao.validar_uso(date(2026, 1, 10)), "")
        self.assertTrue(padrao.validar_uso(date(2026, 9, 9)))

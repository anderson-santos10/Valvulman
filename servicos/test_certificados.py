from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from clientes.models import Cliente

from .models import (
    Calibracao,
    CertificadoCalibracao,
    Instrumento,
    PontoCalibracao,
    ResultadoCalibracao,
    StatusCalibracao,
    StatusCertificado,
    TipoInstrumento,
    UnidadePressao,
)
from .pdf import PdfGenerationError, gerar_pdf_certificado


def preparar_conclusao(calibracao, user):
    calibracao.registrar_execucao(user)
    calibracao.registrar_revisao(user)
    calibracao.save()
    return calibracao


class CertificadoEnsaioTests(TestCase):
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
            tag="PI-01",
            numero_serie="SN-I-100",
            tipo=TipoInstrumento.MANOMETRO,
            fabricante="Wika",
            modelo="233.50",
            faixa_minima=Decimal("0"),
            faixa_maxima=Decimal("10"),
            unidade=UnidadePressao.BAR,
            resolucao=Decimal("0.1"),
        )

    def _concluir(self, indicacao_final="10.05", resultado_esperado=None):
        calibracao = Calibracao.objects.create(
            instrumento=self.instrumento,
            data_calibracao=date(2026, 9, 10),
            procedimento="PROC-CAL-001",
            padrao_utilizado="Fluke 729",
            criterio_aceitacao="Critério interno do cliente",
            tolerancia=Decimal("0.10"),
            observacoes="Ensaio em bancada.",
        )
        PontoCalibracao.objects.create(
            calibracao=calibracao,
            ordem=1,
            valor_referencia=Decimal("0"),
            indicacao_instrumento=Decimal("0.02"),
        )
        PontoCalibracao.objects.create(
            calibracao=calibracao,
            ordem=2,
            valor_referencia=Decimal("10"),
            indicacao_instrumento=Decimal(indicacao_final),
        )
        preparar_conclusao(calibracao, self.user)
        self.client.post(reverse("servicos:concluir_calibracao", args=[calibracao.pk]))
        calibracao.refresh_from_db()
        if resultado_esperado:
            self.assertEqual(calibracao.resultado, resultado_esperado)
        return calibracao

    def test_model_numero_status_e_timestamps(self):
        calibracao = self._concluir(resultado_esperado=ResultadoCalibracao.APROVADO)
        certificado, criado = CertificadoCalibracao.emitir_para(calibracao)
        self.assertTrue(criado)
        self.assertEqual(certificado.numero, "CERT-000001")
        self.assertEqual(certificado.status, StatusCertificado.EMITIDO)
        self.assertEqual(certificado.calibracao, calibracao)
        self.assertIsNotNone(certificado.emitido_em)
        self.assertIsNotNone(certificado.criado_em)
        self.assertIsNotNone(certificado.atualizado_em)
        self.assertTrue(certificado.esta_valido)
        self.assertEqual(calibracao.certificado_atual, certificado)

    def test_emissao_aprovada_cria_certificado_unico(self):
        calibracao = self._concluir(resultado_esperado=ResultadoCalibracao.APROVADO)
        response = self.client.post(
            reverse("servicos:emitir_certificado", args=[calibracao.pk])
        )
        certificado = CertificadoCalibracao.objects.get()
        self.assertEqual(certificado.numero, "CERT-000001")
        self.assertEqual(certificado.status, StatusCertificado.EMITIDO)
        self.assertEqual(certificado.calibracao, calibracao)
        self.assertRedirects(
            response,
            reverse("servicos:detalhe_certificado", args=[certificado.pk]),
        )
        segunda = self.client.post(
            reverse("servicos:emitir_certificado", args=[calibracao.pk])
        )
        self.assertEqual(CertificadoCalibracao.objects.count(), 1)
        self.assertRedirects(
            segunda,
            reverse("servicos:detalhe_certificado", args=[certificado.pk]),
        )

    def test_get_nao_emite(self):
        calibracao = self._concluir()
        response = self.client.get(
            reverse("servicos:emitir_certificado", args=[calibracao.pk])
        )
        self.assertEqual(response.status_code, 405)
        self.assertFalse(CertificadoCalibracao.objects.exists())

    def test_rascunho_e_cancelada_nao_emitem(self):
        rascunho = Calibracao.objects.create(
            instrumento=self.instrumento,
            data_calibracao=date(2026, 9, 10),
            criterio_aceitacao="Critério interno do cliente",
            tolerancia=Decimal("0.10"),
        )
        PontoCalibracao.objects.create(
            calibracao=rascunho,
            ordem=1,
            valor_referencia=Decimal("1"),
            indicacao_instrumento=Decimal("1"),
        )
        self.assertEqual(
            self.client.post(
                reverse("servicos:emitir_certificado", args=[rascunho.pk])
            ).status_code,
            302,
        )
        self.assertFalse(CertificadoCalibracao.objects.exists())

        calibracao = self._concluir()
        self.client.post(reverse("servicos:cancelar_calibracao", args=[calibracao.pk]))
        self.client.post(reverse("servicos:emitir_certificado", args=[calibracao.pk]))
        self.assertFalse(CertificadoCalibracao.objects.exists())

    def test_pendente_nao_emite(self):
        calibracao = Calibracao.objects.create(
            instrumento=self.instrumento,
            data_calibracao=date(2026, 9, 10),
            status=StatusCalibracao.CONCLUIDA,
            resultado=ResultadoCalibracao.PENDENTE,
            criterio_aceitacao="Critério interno do cliente",
            tolerancia=Decimal("0.10"),
        )
        self.client.post(reverse("servicos:emitir_certificado", args=[calibracao.pk]))
        self.assertFalse(CertificadoCalibracao.objects.exists())

    def test_fluxo_completo_aprovado_visualizar_imprimir(self):
        calibracao = self._concluir(resultado_esperado=ResultadoCalibracao.APROVADO)
        self.client.post(reverse("servicos:emitir_certificado", args=[calibracao.pk]))
        certificado = CertificadoCalibracao.objects.get()
        detalhe = self.client.get(
            reverse("servicos:detalhe_certificado", args=[certificado.pk])
        )
        self.assertContains(detalhe, "APROVADO")
        self.assertContains(detalhe, "Indústria Alpha")
        self.assertContains(detalhe, "MAN-001")
        self.assertContains(detalhe, "PI-01")
        self.assertContains(detalhe, "SN-I-100")
        self.assertContains(detalhe, "Wika")
        self.assertContains(detalhe, "233.50")
        self.assertContains(detalhe, "±0.1 bar")
        self.assertContains(detalhe, certificado.numero)
        self.assertContains(detalhe, calibracao.numero)
        self.assertContains(detalhe, "operador")
        self.assertContains(detalhe, "Responsável pela execução")
        self.assertContains(detalhe, "Responsável pela revisão")
        impressao = self.client.get(
            reverse("servicos:imprimir_certificado", args=[certificado.pk])
        )
        self.assertEqual(impressao.status_code, 200)
        self.assertContains(impressao, certificado.numero)
        self.assertNotContains(impressao, "sidebar")

    def test_reprovada_pode_emitir(self):
        calibracao = self._concluir(
            indicacao_final="10.50",
            resultado_esperado=ResultadoCalibracao.REPROVADO,
        )
        self.client.post(reverse("servicos:emitir_certificado", args=[calibracao.pk]))
        certificado = CertificadoCalibracao.objects.get()
        detalhe = self.client.get(
            reverse("servicos:detalhe_certificado", args=[certificado.pk])
        )
        self.assertContains(detalhe, "REPROVADO")
        self.assertContains(detalhe, certificado.numero)

    def test_conteudo_essencial_do_documento(self):
        calibracao = self._concluir()
        self.client.post(reverse("servicos:emitir_certificado", args=[calibracao.pk]))
        certificado = CertificadoCalibracao.objects.get()
        detalhe = self.client.get(
            reverse("servicos:detalhe_certificado", args=[certificado.pk])
        )
        self.assertContains(detalhe, "11.222.333/0001-81")
        self.assertContains(detalhe, "Rua Industrial, 10")
        self.assertContains(detalhe, "PROC-CAL-001")
        self.assertContains(detalhe, "Fluke 729")
        self.assertContains(detalhe, "Critério interno do cliente")
        self.assertContains(detalhe, "Ensaio em bancada.")
        self.assertContains(detalhe, "0.02 bar")
        self.assertContains(detalhe, "10.05 bar")
        self.assertContains(detalhe, "+0.02 bar")
        self.assertContains(detalhe, "+0.05 bar")
        self.assertContains(
            detalhe,
            "O resultado apresentado neste certificado corresponde aos dados registrados",
        )
        self.assertNotContains(detalhe, "INMETRO")
        self.assertNotContains(detalhe, "ISO")

    def test_cancelamento_preserva_e_marca_documento(self):
        calibracao = self._concluir()
        self.client.post(reverse("servicos:emitir_certificado", args=[calibracao.pk]))
        certificado = CertificadoCalibracao.objects.get()
        get_cancel = self.client.get(
            reverse("servicos:cancelar_certificado", args=[certificado.pk])
        )
        self.assertEqual(get_cancel.status_code, 405)
        self.client.post(reverse("servicos:cancelar_certificado", args=[certificado.pk]))
        certificado.refresh_from_db()
        self.assertEqual(certificado.status, StatusCertificado.CANCELADO)
        self.assertTrue(CertificadoCalibracao.objects.filter(pk=certificado.pk).exists())
        self.assertFalse(certificado.esta_valido)
        detalhe = self.client.get(
            reverse("servicos:detalhe_certificado", args=[certificado.pk])
        )
        self.assertContains(detalhe, "CERTIFICADO CANCELADO")
        impressao = self.client.get(
            reverse("servicos:imprimir_certificado", args=[certificado.pk])
        )
        self.assertContains(impressao, "CERTIFICADO CANCELADO")
        self.client.post(reverse("servicos:emitir_certificado", args=[calibracao.pk]))
        self.assertEqual(CertificadoCalibracao.objects.count(), 1)

    def test_reabertura_bloqueada_com_certificado_valido(self):
        calibracao = self._concluir()
        self.client.post(reverse("servicos:emitir_certificado", args=[calibracao.pk]))
        response = self.client.post(
            reverse("servicos:reabrir_calibracao", args=[calibracao.pk])
        )
        calibracao.refresh_from_db()
        self.assertEqual(calibracao.status, StatusCalibracao.CONCLUIDA)
        self.assertRedirects(
            response,
            reverse("servicos:detalhe_calibracao", args=[calibracao.pk]),
        )
        certificado = CertificadoCalibracao.objects.get()
        self.client.post(reverse("servicos:cancelar_certificado", args=[certificado.pk]))
        self.client.post(reverse("servicos:reabrir_calibracao", args=[calibracao.pk]))
        calibracao.refresh_from_db()
        self.assertEqual(calibracao.status, StatusCalibracao.RASCUNHO)

    def test_onetoone_impede_duplicidade(self):
        calibracao = self._concluir()
        CertificadoCalibracao.emitir_para(calibracao)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CertificadoCalibracao.objects.create(
                    calibracao=calibracao,
                    numero="CERT-999999",
                    emitido_em=calibracao.criado_em,
                    status=StatusCertificado.EMITIDO,
                    token_validacao="token-duplicado-teste",
                )

    def test_nao_autenticado_e_404(self):
        calibracao = self._concluir()
        self.client.post(reverse("servicos:emitir_certificado", args=[calibracao.pk]))
        certificado = CertificadoCalibracao.objects.get()
        self.client.logout()
        urls = [
            reverse("servicos:lista_certificados"),
            reverse("servicos:detalhe_certificado", args=[certificado.pk]),
            reverse("servicos:imprimir_certificado", args=[certificado.pk]),
            reverse("servicos:gerar_pdf_certificado", args=[certificado.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("login"), response.url)
        emitir = self.client.post(
            reverse("servicos:emitir_certificado", args=[calibracao.pk])
        )
        self.assertEqual(emitir.status_code, 302)
        self.assertIn(reverse("login"), emitir.url)
        self.client.login(username="operador", password="senha-segura-123")
        self.assertEqual(
            self.client.get(
                reverse("servicos:detalhe_certificado", args=[99999])
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse("servicos:emitir_certificado", args=[99999])
            ).status_code,
            404,
        )

    def test_historico_do_instrumento_mostra_certificado(self):
        calibracao = self._concluir()
        self.client.post(reverse("servicos:emitir_certificado", args=[calibracao.pk]))
        certificado = CertificadoCalibracao.objects.get()
        historico = self.client.get(
            reverse("servicos:detalhe_instrumento", args=[self.instrumento.pk])
        )
        self.assertContains(historico, certificado.numero)
        lista = self.client.get(reverse("servicos:lista_certificados"))
        self.assertContains(lista, certificado.numero)
        self.assertContains(lista, "Indústria Alpha")
        detalhe_cal = self.client.get(
            reverse("servicos:detalhe_calibracao", args=[calibracao.pk])
        )
        self.assertContains(detalhe_cal, certificado.numero)
        self.assertContains(detalhe_cal, "Visualizar certificado")


class CertificadoEnsaioPdfTests(TestCase):
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
            tag="PI-01",
            numero_serie="SN-I-100",
            tipo=TipoInstrumento.MANOMETRO,
            fabricante="Wika",
            modelo="233.50",
            faixa_minima=Decimal("0"),
            faixa_maxima=Decimal("10"),
            unidade=UnidadePressao.BAR,
            resolucao=Decimal("0.1"),
        )

    def _concluir(self, indicacao_final="10.05", extra_pontos=0, **extra):
        dados = {
            "instrumento": self.instrumento,
            "data_calibracao": date(2026, 9, 10),
            "procedimento": "PROC-CAL-001",
            "padrao_utilizado": "Fluke 729",
            "criterio_aceitacao": "Critério interno do cliente",
            "tolerancia": Decimal("0.10"),
            "observacoes": "Ensaio em bancada.",
        }
        dados.update(extra)
        calibracao = Calibracao.objects.create(**dados)
        PontoCalibracao.objects.create(
            calibracao=calibracao,
            ordem=1,
            valor_referencia=Decimal("0"),
            indicacao_instrumento=Decimal("0.02"),
        )
        for ordem in range(2, extra_pontos + 2):
            referencia = Decimal(ordem)
            PontoCalibracao.objects.create(
                calibracao=calibracao,
                ordem=ordem,
                valor_referencia=referencia,
                indicacao_instrumento=referencia + Decimal("0.03"),
            )
        ultima_ordem = extra_pontos + 2
        PontoCalibracao.objects.create(
            calibracao=calibracao,
            ordem=ultima_ordem,
            valor_referencia=Decimal("10"),
            indicacao_instrumento=Decimal(indicacao_final),
        )
        preparar_conclusao(calibracao, self.user)
        self.client.post(reverse("servicos:concluir_calibracao", args=[calibracao.pk]))
        calibracao.refresh_from_db()
        self.client.post(reverse("servicos:emitir_certificado", args=[calibracao.pk]))
        return calibracao, CertificadoCalibracao.objects.get()

    def _texto_pdf(self, conteudo):
        from io import BytesIO

        from pypdf import PdfReader

        leitor = PdfReader(BytesIO(conteudo))
        return "\n".join((pagina.extract_text() or "") for pagina in leitor.pages), leitor

    def test_pdf_aprovado_valido_sem_alterar_banco(self):
        calibracao, certificado = self._concluir()
        emitido_em = certificado.emitido_em
        atualizado_em = certificado.atualizado_em
        total_certificados = CertificadoCalibracao.objects.count()
        total_pontos = PontoCalibracao.objects.count()
        response = self.client.get(
            reverse("servicos:gerar_pdf_certificado", args=[certificado.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertIn(
            "Certificado_CERT-000001.pdf",
            response["Content-Disposition"],
        )
        texto, leitor = self._texto_pdf(response.content)
        self.assertGreaterEqual(len(leitor.pages), 1)
        self.assertIn("CERTIFICADO DE CALIBRAÇÃO", texto)
        self.assertIn("CERT-000001", texto)
        self.assertIn("Indústria Alpha", texto)
        self.assertIn("MAN-001", texto)
        self.assertIn("0 a 10 bar", texto)
        self.assertIn("±0.1 bar", texto)
        self.assertIn("APROVADO", texto.upper())
        self.assertIn("operador", texto)
        self.assertIn("Calibração", texto)
        metadados = leitor.metadata or {}
        self.assertIn("CERT-000001", str(metadados.title or ""))
        certificado.refresh_from_db()
        calibracao.refresh_from_db()
        self.assertEqual(certificado.emitido_em, emitido_em)
        self.assertEqual(certificado.atualizado_em, atualizado_em)
        self.assertEqual(CertificadoCalibracao.objects.count(), total_certificados)
        self.assertEqual(PontoCalibracao.objects.count(), total_pontos)
        self.assertEqual(calibracao.resultado, ResultadoCalibracao.APROVADO)

    def test_pdf_reprovado_e_cancelado(self):
        calibracao, certificado = self._concluir(indicacao_final="10.50")
        pdf_reprovado = self.client.get(
            reverse("servicos:gerar_pdf_certificado", args=[certificado.pk])
        )
        texto_reprovado, _ = self._texto_pdf(pdf_reprovado.content)
        self.assertIn("REPROVADO", texto_reprovado.upper())
        self.client.post(reverse("servicos:cancelar_certificado", args=[certificado.pk]))
        pdf_cancelado = self.client.get(
            reverse("servicos:gerar_pdf_certificado", args=[certificado.pk])
        )
        self.assertEqual(pdf_cancelado.status_code, 200)
        texto_cancelado, _ = self._texto_pdf(pdf_cancelado.content)
        self.assertIn("CERTIFICADO CANCELADO", texto_cancelado)
        self.assertEqual(CertificadoCalibracao.objects.count(), 1)

    def test_pdf_muitos_pontos_quebra_pagina(self):
        _, certificado = self._concluir(extra_pontos=60)
        response = self.client.get(
            reverse("servicos:gerar_pdf_certificado", args=[certificado.pk])
        )
        self.assertEqual(response.status_code, 200)
        texto, leitor = self._texto_pdf(response.content)
        self.assertGreaterEqual(len(leitor.pages), 2)
        self.assertIn("Ponto", texto)
        self.assertIn("Referência", texto)
        self.assertTrue(any("60" in (pagina.extract_text() or "") for pagina in leitor.pages))

    def test_pdf_seis_pontos_uma_pagina(self):
        _, certificado = self._concluir(
            extra_pontos=4,
            intervalo_validade_meses=12,
        )
        self.assertEqual(certificado.calibracao.pontos.count(), 6)
        response = self.client.get(
            reverse("servicos:gerar_pdf_certificado", args=[certificado.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
        texto, leitor = self._texto_pdf(response.content)
        self.assertEqual(len(leitor.pages), 1)
        self.assertIn("CERT-000001", texto)
        self.assertIn("PROC-CAL-001", texto)
        self.assertIn("12 meses", texto)
        self.assertIn("bar", texto.lower())
        self.assertIn("operador", texto)
        self.assertIn("APROVADO", texto.upper())

    def test_pdf_404_e_get_nao_cria_certificado(self):
        self.assertEqual(
            self.client.get(reverse("servicos:gerar_pdf_certificado", args=[99999])).status_code,
            404,
        )
        self.assertFalse(CertificadoCalibracao.objects.exists())

    def test_fluxo_completo_ate_pdf(self):
        calibracao, certificado = self._concluir()
        self.assertEqual(
            self.client.get(
                reverse("servicos:detalhe_certificado", args=[certificado.pk])
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                reverse("servicos:imprimir_certificado", args=[certificado.pk])
            ).status_code,
            200,
        )
        pdf = self.client.get(
            reverse("servicos:gerar_pdf_certificado", args=[certificado.pk])
        )
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        self.assertEqual(calibracao.numero, "CAL-0001")
        self.assertEqual(certificado.numero, "CERT-000001")

    def _falha_pdf_com_causa(self, *_args, **_kwargs):
        try:
            raise OSError("chromium ausente")
        except OSError as exc:
            raise PdfGenerationError(
                "Falha ao renderizar o PDF do certificado."
            ) from exc

    @patch("servicos.views.gerar_pdf_certificado")
    def test_pdf_erro_producao_nao_expoe_causa(self, mock_pdf):
        mock_pdf.side_effect = self._falha_pdf_com_causa
        _, certificado = self._concluir()
        with self.settings(DEBUG=False):
            with self.assertLogs("servicos.views", level="ERROR") as registros:
                response = self.client.get(
                    reverse("servicos:gerar_pdf_certificado", args=[certificado.pk]),
                    follow=True,
                )
        self.assertContains(
            response,
            "Não foi possível gerar o PDF do certificado. Tente novamente.",
        )
        self.assertNotContains(response, "chromium ausente")
        texto_log = "\n".join(registros.output)
        self.assertIn(certificado.numero, texto_log)
        self.assertIn("CAL-0001", texto_log)
        self.assertIn("chromium ausente", texto_log)

    @patch("servicos.views.gerar_pdf_certificado")
    def test_pdf_erro_debug_mostra_causa(self, mock_pdf):
        mock_pdf.side_effect = self._falha_pdf_com_causa
        _, certificado = self._concluir()
        with self.settings(DEBUG=True):
            response = self.client.get(
                reverse("servicos:gerar_pdf_certificado", args=[certificado.pk]),
                follow=True,
            )
        self.assertContains(
            response, "Não foi possível gerar o PDF do certificado. Tente novamente."
        )
        self.assertContains(response, "chromium ausente")

    def test_pdf_generation_error_preserva_causa(self):
        with self.assertRaises(PdfGenerationError) as capturado:
            try:
                raise OSError("chromium ausente")
            except OSError as exc:
                raise PdfGenerationError(
                    "Falha ao renderizar o PDF do certificado."
                ) from exc
        self.assertIsInstance(capturado.exception.__cause__, OSError)
        self.assertEqual(str(capturado.exception.__cause__), "chromium ausente")

    @patch("servicos.pdf._html_para_pdf", side_effect=RuntimeError("falha inesperada"))
    def test_gerar_pdf_empacota_excecao_inesperada(self, _mock_html):
        _, certificado = self._concluir()
        with self.assertRaises(PdfGenerationError) as capturado:
            gerar_pdf_certificado(certificado)
        self.assertIsInstance(capturado.exception.__cause__, RuntimeError)
        self.assertEqual(str(capturado.exception.__cause__), "falha inesperada")


class CertificadoValidacaoPublicaTests(TestCase):
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
            tag="PI-01",
            tipo=TipoInstrumento.MANOMETRO,
            fabricante="Wika",
            modelo="233.50",
            faixa_minima=Decimal("0"),
            faixa_maxima=Decimal("10"),
            unidade=UnidadePressao.BAR,
        )

    def _emitir(self):
        calibracao = Calibracao.objects.create(
            instrumento=self.instrumento,
            data_calibracao=date(2026, 9, 10),
            criterio_aceitacao="Critério interno do cliente",
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
        return CertificadoCalibracao.objects.get()

    def test_token_unico_imprevisivel_e_estavel(self):
        certificado = self._emitir()
        self.assertTrue(certificado.token_validacao)
        self.assertNotEqual(certificado.token_validacao, certificado.numero)
        self.assertNotEqual(certificado.token_validacao, str(certificado.pk))
        self.assertGreaterEqual(len(certificado.token_validacao), 32)
        token = certificado.token_validacao
        self.client.get(reverse("servicos:gerar_pdf_certificado", args=[certificado.pk]))
        certificado.refresh_from_db()
        self.assertEqual(certificado.token_validacao, token)

    def test_validacao_publica_sem_login(self):
        certificado = self._emitir()
        self.client.logout()
        url = reverse("validar_certificado", args=[certificado.token_validacao])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CERTIFICADO VÁLIDO")
        self.assertContains(response, certificado.numero)
        self.assertContains(response, "MAN-001")
        self.assertNotContains(response, "Ensaio em bancada")
        self.assertEqual(
            self.client.post(url).status_code,
            405,
        )

    def test_validacao_cancelado_e_token_invalido(self):
        certificado = self._emitir()
        self.client.post(reverse("servicos:cancelar_certificado", args=[certificado.pk]))
        self.client.logout()
        response = self.client.get(
            reverse("validar_certificado", args=[certificado.token_validacao])
        )
        self.assertContains(response, "CERTIFICADO CANCELADO")
        self.assertNotContains(response, "CERTIFICADO VÁLIDO")
        inexistente = self.client.get(reverse("validar_certificado", args=["inexistente"]))
        self.assertEqual(inexistente.status_code, 404)
        self.assertContains(inexistente, "CERTIFICADO NÃO ENCONTRADO", status_code=404)

    def test_qr_no_html_e_no_pdf(self):
        certificado = self._emitir()
        detalhe = self.client.get(
            reverse("servicos:detalhe_certificado", args=[certificado.pk])
        )
        self.assertContains(detalhe, "data:image/svg+xml")
        self.assertContains(detalhe, "/validar/")
        from servicos.pdf import _renderizar_html

        html = _renderizar_html(certificado)
        self.assertIn("data:image/svg+xml", html)
        self.assertIn(certificado.token_validacao, html)
        pdf = self.client.get(
            reverse("servicos:gerar_pdf_certificado", args=[certificado.pk])
        )
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_validade_no_certificado_html_pdf_e_pagina_publica(self):
        calibracao = Calibracao.objects.create(
            instrumento=self.instrumento,
            data_calibracao=date(2026, 9, 9),
            criterio_aceitacao="Critério interno do cliente",
            tolerancia=Decimal("0.10"),
            intervalo_validade_meses=12,
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
        calibracao.refresh_from_db()
        self.assertEqual(calibracao.data_validade, date(2027, 9, 9))
        certificado = CertificadoCalibracao.objects.get()
        detalhe = self.client.get(
            reverse("servicos:detalhe_certificado", args=[certificado.pk])
        )
        self.assertContains(detalhe, "09/09/2026")
        self.assertContains(detalhe, "Validade")
        self.assertContains(detalhe, "09/09/2027")
        self.assertContains(detalhe, "Próxima calibração")
        from servicos.pdf import _renderizar_html

        html = _renderizar_html(certificado)
        self.assertIn("09/09/2027", html)
        self.client.logout()
        publico = self.client.get(
            reverse("validar_certificado", args=[certificado.token_validacao])
        )
        self.assertContains(publico, "CERTIFICADO VÁLIDO")
        self.assertContains(publico, "09/09/2027")
        with patch("servicos.models.timezone.localdate", return_value=date(2027, 9, 10)):
            expirado = self.client.get(
                reverse("validar_certificado", args=[certificado.token_validacao])
            )
        self.assertContains(expirado, "CERTIFICADO EMITIDO — VALIDADE EXPIRADA")
        self.assertNotContains(expirado, "CERTIFICADO CANCELADO")
        self.client.login(username="operador", password="senha-segura-123")
        self.client.post(reverse("servicos:cancelar_certificado", args=[certificado.pk]))
        self.client.logout()
        with patch("servicos.models.timezone.localdate", return_value=date(2027, 9, 10)):
            cancelado = self.client.get(
                reverse("validar_certificado", args=[certificado.token_validacao])
            )
        self.assertContains(cancelado, "CERTIFICADO CANCELADO")
        self.assertNotContains(cancelado, "CERTIFICADO VÁLIDO")
        self.assertNotContains(cancelado, "VALIDADE EXPIRADA")

    def test_sem_intervalo_nao_inventa_validade(self):
        certificado = self._emitir()
        self.assertIsNone(certificado.calibracao.data_validade)
        detalhe = self.client.get(
            reverse("servicos:detalhe_certificado", args=[certificado.pk])
        )
        self.assertContains(detalhe, "Intervalo")
        self.assertContains(detalhe, "Próxima calibração")
        self.assertNotContains(detalhe, "13/09/2027")



from datetime import date
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import Permission, User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse

from clientes.models import Cliente

from .demo_metrologia import (
    CRITERIO_DEMO,
    PADRAO_DEMO_CODIGO,
    PADRAO_DEMO_NOME,
    PROCEDIMENTO_DEMO_CODIGO,
)
from .models import (
    Calibracao,
    CertificadoCalibracao,
    Instrumento,
    ItemOrdemServico,
    OrdemServico,
    PadraoMedicao,
    ResultadoCalibracao,
    ServicoSolicitado,
    StatusCalibracao,
    StatusItemOrdem,
    StatusOrdemServico,
    TipoEquipamento,
    TipoInstrumento,
    UnidadePressao,
)


class SeedMetrologiaDemoTests(TestCase):
    @override_settings(DEBUG=False)
    def test_seed_bloqueado_sem_debug(self):
        with self.assertRaises(CommandError):
            call_command("seed_metrologia_demo")
        self.assertFalse(PadraoMedicao.objects.exists())

    @override_settings(DEBUG=True)
    def test_seed_cria_padrao_demo_idempotente(self):
        saida = StringIO()
        call_command("seed_metrologia_demo", stdout=saida)
        call_command("seed_metrologia_demo", stdout=saida)
        self.assertEqual(PadraoMedicao.objects.count(), 1)
        padrao = PadraoMedicao.objects.get(codigo=PADRAO_DEMO_CODIGO)
        self.assertEqual(padrao.identificacao, PADRAO_DEMO_NOME)
        self.assertTrue(padrao.ativo)
        self.assertIsNone(padrao.data_validade)
        self.assertIn("Não é padrão rastreável", padrao.observacoes)
        texto = saida.getvalue()
        self.assertIn(PROCEDIMENTO_DEMO_CODIGO, texto)
        self.assertIn(CRITERIO_DEMO, texto)
        self.assertIn("Não são rastreáveis", texto)


class FluxoCalibracaoOsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="operador",
            email="operador@example.com",
            password="senha-segura-123",
        )
        self.client.login(username="operador", password="senha-segura-123")
        self.cliente = Cliente.objects.create(
            nome="Laboratório Simulação",
            cnpj="11.222.333/0001-81",
            cep="17512-400",
            endereco="Rua Industrial, 10",
        )
        self.instrumento = Instrumento.objects.create(
            cliente=self.cliente,
            codigo="INS-0001",
            tipo=TipoInstrumento.MANOMETRO,
            faixa_minima=Decimal("0"),
            faixa_maxima=Decimal("10"),
            unidade=UnidadePressao.BAR,
        )
        self.ordem = OrdemServico.criar(
            cliente=self.cliente,
            data_entrada=date(2026, 9, 13),
            status=StatusOrdemServico.RECEBIDA,
        )
        self.item = ItemOrdemServico.objects.create(
            ordem_servico=self.ordem,
            tipo_equipamento=TipoEquipamento.INSTRUMENTO,
            instrumento=self.instrumento,
            servico_solicitado=ServicoSolicitado.CALIBRACAO,
            condicao_recebimento="Bom estado",
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
            dados[f"{prefixo}-observacoes"] = ponto.get("observacoes", "")
            if ponto.get("id"):
                dados[f"{prefixo}-id"] = str(ponto["id"])
        return dados

    def _pontos_demo(self, indicacoes=None):
        refs = [0, 2, 4, 6, 8, 10]
        if indicacoes is None:
            indicacoes = refs
        return [
            {
                "ordem": indice + 1,
                "valor_referencia": str(ref),
                "indicacao_instrumento": str(indicacoes[indice]),
                "observacoes": "Ponto DEMO de software",
            }
            for indice, ref in enumerate(refs)
        ]

    def _iniciar(self):
        self.client.post(reverse("servicos:iniciar_item_ordem", args=[self.item.pk]))
        return Calibracao.objects.get(item_ordem_servico=self.item)

    def test_edicao_sem_padrao_orienta_cadastro(self):
        calibracao = self._iniciar()
        pagina = self.client.get(
            reverse("servicos:editar_calibracao", args=[calibracao.pk])
        )
        self.assertContains(pagina, "Nenhum padrão de medição ativo cadastrado")
        self.assertContains(pagina, reverse("servicos:cadastrar_padrao"))
        self.assertContains(pagina, PROCEDIMENTO_DEMO_CODIGO)
        self.assertContains(
            pagina, reverse("servicos:detalhe_item_ordem", args=[self.item.pk])
        )

    def test_empty_form_de_pontos_usa_template_com_tr(self):
        calibracao = self._iniciar()
        pagina = self.client.get(
            reverse("servicos:editar_calibracao", args=[calibracao.pk])
        )
        html = pagina.content.decode()
        self.assertIn('<template id="ponto-empty-form">', html)
        self.assertNotIn('<div id="ponto-empty-form"', html)
        self.assertIn('id="btn-add-ponto"', html)
        self.assertIn('id="id_pontos-TOTAL_FORMS"', html)
        inicio = html.find('<template id="ponto-empty-form">')
        fim = html.find("</template>", inicio)
        molde = html[inicio:fim]
        self.assertIn("<tr", molde)
        self.assertIn('name="pontos-__prefix__-ordem"', molde)
        self.assertIn('name="pontos-__prefix__-valor_referencia"', molde)
        self.assertIn('name="pontos-__prefix__-indicacao_instrumento"', molde)
        self.assertIn('name="pontos-__prefix__-observacoes"', molde)
        self.assertIn('name="pontos-__prefix__-id"', molde)
        self.assertIn('name="pontos-__prefix__-DELETE"', molde)

    def test_fluxo_completo_aprovado_revisao_os_e_certificado(self):
        padrao = PadraoMedicao.objects.create(
            codigo=PADRAO_DEMO_CODIGO,
            identificacao=PADRAO_DEMO_NOME,
            unidade=UnidadePressao.BAR,
            faixa_minima=Decimal("0"),
            faixa_maxima=Decimal("16"),
            ativo=True,
        )
        calibracao = self._iniciar()
        self.assertEqual(calibracao.instrumento_id, self.instrumento.pk)
        dados = {
            "instrumento": self.instrumento.pk,
            "item_ordem_servico": self.item.pk,
            "numero": calibracao.numero,
            "data_calibracao": "2026-09-13",
            "procedimento": PROCEDIMENTO_DEMO_CODIGO,
            "padrao": padrao.pk,
            "criterio_aceitacao": CRITERIO_DEMO,
            "tolerancia": "0.10",
            "intervalo_validade_meses": "12",
            "observacoes": "Ensaio DEMO de software",
        }
        dados.update(self._formset(self._pontos_demo()))
        salvar = self.client.post(
            reverse("servicos:editar_calibracao", args=[calibracao.pk]),
            dados,
        )
        self.assertRedirects(
            salvar, reverse("servicos:detalhe_calibracao", args=[calibracao.pk])
        )
        calibracao.refresh_from_db()
        self.assertEqual(calibracao.procedimento, PROCEDIMENTO_DEMO_CODIGO)
        self.assertEqual(calibracao.padrao_id, padrao.pk)
        self.assertEqual(calibracao.criterio_aceitacao, CRITERIO_DEMO)
        self.assertEqual(calibracao.tolerancia, Decimal("0.100"))
        self.assertEqual(calibracao.pontos.count(), 6)
        self.assertEqual(calibracao.pontos.get(ordem=2).erro, Decimal("0.000"))
        self.assertEqual(calibracao.resultado, ResultadoCalibracao.PENDENTE)

        detalhe = self.client.get(
            reverse("servicos:detalhe_calibracao", args=[calibracao.pk])
        )
        self.assertContains(detalhe, "Enviar para revisão")
        self.assertContains(detalhe, "Voltar ao item")

        incompleta = Calibracao.objects.create(
            instrumento=self.instrumento,
            data_calibracao=date(2026, 9, 13),
            criterio_aceitacao="",
            tolerancia=None,
        )
        revisar_incompleta = self.client.post(
            reverse("servicos:revisar_calibracao", args=[incompleta.pk])
        )
        self.assertRedirects(
            revisar_incompleta,
            reverse("servicos:editar_calibracao", args=[incompleta.pk]),
        )
        incompleta.refresh_from_db()
        self.assertFalse(incompleta.esta_revisada)

        self.client.post(reverse("servicos:revisar_calibracao", args=[calibracao.pk]))
        calibracao.refresh_from_db()
        self.item.refresh_from_db()
        self.ordem.refresh_from_db()
        self.assertTrue(calibracao.esta_revisada)
        self.assertEqual(self.item.status, StatusItemOrdem.AGUARDANDO_REVISAO)
        self.assertEqual(self.ordem.status, StatusOrdemServico.AGUARDANDO_REVISAO)

        self.client.post(reverse("servicos:concluir_calibracao", args=[calibracao.pk]))
        calibracao.refresh_from_db()
        self.item.refresh_from_db()
        self.ordem.refresh_from_db()
        self.assertEqual(calibracao.status, StatusCalibracao.CONCLUIDA)
        self.assertEqual(calibracao.resultado, ResultadoCalibracao.APROVADO)
        self.assertEqual(self.item.status, StatusItemOrdem.CONCLUIDO)
        self.assertEqual(self.ordem.status, StatusOrdemServico.CONCLUIDA)

        emitir = self.client.post(
            reverse("servicos:emitir_certificado", args=[calibracao.pk])
        )
        certificado = CertificadoCalibracao.objects.get(calibracao=calibracao)
        self.assertRedirects(
            emitir, reverse("servicos:detalhe_certificado", args=[certificado.pk])
        )
        self.assertTrue(certificado.numero.startswith("CERT-"))

    def test_resultado_reprovado_pelos_pontos(self):
        PadraoMedicao.objects.create(
            codigo="PAD-TEST-001",
            identificacao="Padrão de teste",
            ativo=True,
        )
        calibracao = self._iniciar()
        padrao = PadraoMedicao.objects.get(codigo="PAD-TEST-001")
        indicacoes = [0, 2, 4, 6, 8, 10.5]
        dados = {
            "instrumento": self.instrumento.pk,
            "item_ordem_servico": self.item.pk,
            "numero": calibracao.numero,
            "data_calibracao": "2026-09-13",
            "procedimento": PROCEDIMENTO_DEMO_CODIGO,
            "padrao": padrao.pk,
            "criterio_aceitacao": CRITERIO_DEMO,
            "tolerancia": "0.10",
        }
        dados.update(self._formset(self._pontos_demo(indicacoes)))
        self.client.post(
            reverse("servicos:editar_calibracao", args=[calibracao.pk]),
            dados,
        )
        ponto = calibracao.pontos.get(ordem=6)
        self.assertEqual(ponto.erro, Decimal("0.500"))
        self.assertFalse(ponto.dentro_da_tolerancia)
        self.client.post(reverse("servicos:revisar_calibracao", args=[calibracao.pk]))
        self.client.post(reverse("servicos:concluir_calibracao", args=[calibracao.pk]))
        calibracao.refresh_from_db()
        self.assertEqual(calibracao.resultado, ResultadoCalibracao.REPROVADO)

    def test_edicao_de_ponto_recalcula_erro(self):
        calibracao = self._iniciar()
        dados = {
            "instrumento": self.instrumento.pk,
            "item_ordem_servico": self.item.pk,
            "numero": calibracao.numero,
            "data_calibracao": "2026-09-13",
            "criterio_aceitacao": CRITERIO_DEMO,
            "tolerancia": "0.10",
        }
        dados.update(
            self._formset(
                [
                    {
                        "ordem": 1,
                        "valor_referencia": "0",
                        "indicacao_instrumento": "0",
                    }
                ]
            )
        )
        self.client.post(
            reverse("servicos:editar_calibracao", args=[calibracao.pk]),
            dados,
        )
        ponto = calibracao.pontos.get()
        dados["pontos-INITIAL_FORMS"] = "1"
        dados["pontos-0-id"] = str(ponto.pk)
        dados["pontos-0-indicacao_instrumento"] = "0.05"
        self.client.post(
            reverse("servicos:editar_calibracao", args=[calibracao.pk]),
            dados,
        )
        ponto.refresh_from_db()
        self.assertEqual(ponto.erro, Decimal("0.050"))

    def test_revisao_exige_permissao(self):
        calibracao = self._iniciar()
        tecnico = User.objects.create_user(
            username="tecnico-sem-revisao",
            password="senha-segura-123",
        )
        for codename in ("view_calibracao", "change_calibracao"):
            tecnico.user_permissions.add(
                Permission.objects.get(
                    codename=codename,
                    content_type__app_label="servicos",
                )
            )
        self.client.login(username="tecnico-sem-revisao", password="senha-segura-123")
        response = self.client.post(
            reverse("servicos:revisar_calibracao", args=[calibracao.pk])
        )
        self.assertEqual(response.status_code, 403)
        calibracao.refresh_from_db()
        self.assertFalse(calibracao.esta_revisada)

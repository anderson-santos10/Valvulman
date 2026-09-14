from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from clientes.models import Cliente

from .models import (
    Calibracao,
    CertificadoCalibracao,
    Instrumento,
    ItemOrdemServico,
    OrdemServico,
    StatusCalibracao,
    StatusItemOrdem,
    StatusOrdemServico,
    TipoInstrumento,
    UnidadePressao,
)
from .operacao import indicadores_operacao, queryset_instrumentos_vencidos, queryset_ordens_atrasadas


class OperacaoHistoricoTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="operador",
            email="operador@example.com",
            password="senha-segura-123",
        )
        self.client.login(username="operador", password="senha-segura-123")
        self.hoje = timezone.localdate()
        self.ontem = self.hoje - timedelta(days=1)
        self.amanha = self.hoje + timedelta(days=1)
        self.cliente = Cliente.objects.create(
            nome="Empresa ABC",
            cnpj="11.222.333/0001-81",
            cep="17512-400",
            endereco="Rua Industrial, 10",
        )
        self.instrumento = Instrumento.objects.create(
            cliente=self.cliente,
            codigo="MAN-001",
            tag="PI-01",
            numero_serie="SN-001",
            tipo=TipoInstrumento.MANOMETRO,
            faixa_minima=Decimal("0"),
            faixa_maxima=Decimal("10"),
            unidade=UnidadePressao.BAR,
        )

    def _ordem(self, status=StatusOrdemServico.ABERTA, previsao=None, **extra):
        dados = {
            "cliente": self.cliente,
            "data_entrada": extra.pop("data_entrada", self.hoje),
            "data_previsao_entrega": previsao,
            "status": status,
        }
        dados.update(extra)
        return OrdemServico.criar(**dados)

    def test_atraso_calculado(self):
        aberta = self._ordem(previsao=self.ontem)
        entregue = self._ordem(
            status=StatusOrdemServico.ENTREGUE,
            previsao=self.ontem,
            data_entrega=self.hoje,
        )
        cancelada = self._ordem(
            status=StatusOrdemServico.CANCELADA,
            previsao=self.ontem,
        )
        sem_previsao = self._ordem()
        self.assertTrue(aberta.esta_atrasada)
        self.assertFalse(entregue.esta_atrasada)
        self.assertFalse(cancelada.esta_atrasada)
        self.assertFalse(sem_previsao.esta_atrasada)
        atrasadas = queryset_ordens_atrasadas()
        self.assertEqual(set(atrasadas), {aberta})

    def test_dashboard_contagens_os(self):
        self._ordem(StatusOrdemServico.ABERTA)
        self._ordem(StatusOrdemServico.EM_EXECUCAO)
        self._ordem(StatusOrdemServico.AGUARDANDO_REVISAO)
        self._ordem(StatusOrdemServico.CONCLUIDA)
        self._ordem(
            StatusOrdemServico.ENTREGUE,
            data_entrega=self.hoje,
        )
        self._ordem(StatusOrdemServico.ABERTA, previsao=self.ontem)
        indicadores = indicadores_operacao(hoje=self.hoje)
        home = self.client.get(reverse("home"))
        self.assertEqual(home.status_code, 200)
        self.assertEqual(indicadores["os_abertas"], 2)
        self.assertEqual(indicadores["os_em_execucao"], 1)
        self.assertEqual(indicadores["os_aguardando_revisao"], 1)
        self.assertEqual(indicadores["os_concluidas"], 1)
        self.assertEqual(indicadores["os_entregues"], 1)
        self.assertEqual(indicadores["os_atrasadas"], 1)
        self.assertContains(home, "OS atrasadas")
        self.assertContains(home, "OS por situação")
        self.assertNotContains(home, "Instrumentos com calibração vencida")
        self.assertNotContains(home, "data-chart=\"calibracoes\"")

    def test_lista_filtros_periodo_atrasadas_e_cnpj(self):
        atual = self._ordem(previsao=self.ontem, data_entrada=self.hoje)
        antiga = self._ordem(data_entrada=self.hoje - timedelta(days=40))
        lista = self.client.get(
            reverse("servicos:lista_ordens"),
            {
                "q": "11.222.333",
                "atrasadas": "1",
                "data_de": self.hoje.isoformat(),
                "data_ate": self.hoje.isoformat(),
            },
        )
        self.assertContains(lista, atual.numero)
        self.assertNotContains(lista, antiga.numero)

    def test_detalhe_os_progresso(self):
        ordem = self._ordem(StatusOrdemServico.EM_EXECUCAO)
        ItemOrdemServico.objects.create(
            ordem_servico=ordem,
            instrumento=self.instrumento,
            status=StatusItemOrdem.CONCLUIDO,
        )
        outro = Instrumento.objects.create(
            cliente=self.cliente,
            codigo="MAN-002",
            tipo=TipoInstrumento.MANOMETRO,
            faixa_minima=Decimal("0"),
            faixa_maxima=Decimal("16"),
            unidade=UnidadePressao.BAR,
        )
        ItemOrdemServico.objects.create(
            ordem_servico=ordem,
            instrumento=outro,
            status=StatusItemOrdem.EM_EXECUCAO,
        )
        detalhe = self.client.get(reverse("servicos:detalhe_ordem", args=[ordem.pk]))
        self.assertContains(detalhe, "1 de 2 itens concluídos")
        self.assertContains(detalhe, "50%")

    def test_fila_organiza_por_status(self):
        aberta = self._ordem(StatusOrdemServico.ABERTA)
        execucao = self._ordem(StatusOrdemServico.EM_EXECUCAO)
        revisao = self._ordem(StatusOrdemServico.AGUARDANDO_REVISAO)
        concluida = self._ordem(StatusOrdemServico.CONCLUIDA)
        entregue = self._ordem(
            StatusOrdemServico.ENTREGUE,
            data_entrega=self.hoje,
        )
        cancelada = self._ordem(StatusOrdemServico.CANCELADA)
        fila = self.client.get(reverse("servicos:fila_ordens"))
        html = fila.content.decode()
        self.assertIn("Aguardando execução", html)
        self.assertLess(html.index(aberta.numero), html.index(execucao.numero))
        self.assertContains(fila, execucao.numero)
        self.assertContains(fila, revisao.numero)
        self.assertContains(fila, concluida.numero)
        self.assertContains(fila, entregue.numero)
        self.assertContains(fila, cancelada.numero)
        self.assertContains(fila, "Iniciar")
        self.assertContains(fila, "Entregar")
        get_iniciar = self.client.get(
            reverse("servicos:iniciar_ordem", args=[aberta.pk])
        )
        self.assertEqual(get_iniciar.status_code, 405)

    def test_fila_exige_login_e_csrf(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("servicos:fila_ordens")).status_code, 302)
        self.client.login(username="operador", password="senha-segura-123")
        ordem = self._ordem()
        cliente_csrf = Client(enforce_csrf_checks=True)
        cliente_csrf.login(username="operador", password="senha-segura-123")
        response = cliente_csrf.post(
            reverse("servicos:iniciar_ordem", args=[ordem.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_ultima_calibracao_usa_data_calibracao(self):
        antiga = Calibracao.objects.create(
            instrumento=self.instrumento,
            data_calibracao=self.hoje - timedelta(days=20),
            intervalo_validade_meses=12,
        )
        recente = Calibracao.objects.create(
            instrumento=self.instrumento,
            data_calibracao=self.hoje,
            intervalo_validade_meses=12,
        )
        antiga.data_calibracao = self.hoje - timedelta(days=400)
        antiga.save(update_fields=["data_calibracao"])
        self.assertEqual(self.instrumento.ultima_calibracao(), recente)

    def test_situacao_validade_sem_inventar_janela(self):
        self.assertEqual(self.instrumento.situacao_calibracao_codigo, "sem_calibracao")
        sem_validade = Calibracao.objects.create(
            instrumento=self.instrumento,
            data_calibracao=self.hoje,
        )
        self.assertEqual(self.instrumento.situacao_calibracao_codigo, "sem_validade")
        self.assertFalse(queryset_instrumentos_vencidos().filter(pk=self.instrumento.pk).exists())
        sem_validade.data_validade = self.amanha
        sem_validade.save(update_fields=["data_validade"])
        self.assertEqual(self.instrumento.situacao_calibracao_codigo, "valida")
        sem_validade.data_validade = self.ontem
        sem_validade.save(update_fields=["data_validade"])
        self.assertEqual(self.instrumento.situacao_calibracao_codigo, "vencida")
        self.assertTrue(queryset_instrumentos_vencidos().filter(pk=self.instrumento.pk).exists())
        home = self.client.get(reverse("home"))
        self.assertEqual(home.context["indicadores"]["instrumentos_vencidos"], 1)
        self.assertContains(home, "Instrumentos com calibração vencida")

    def test_historico_instrumento_cliente_e_certificado(self):
        ordem = self._ordem()
        item = ItemOrdemServico.objects.create(
            ordem_servico=ordem,
            instrumento=self.instrumento,
        )
        calibracao = Calibracao.objects.create(
            instrumento=self.instrumento,
            item_ordem_servico=item,
            data_calibracao=self.hoje,
            status=StatusCalibracao.CONCLUIDA,
            resultado="aprovado",
            intervalo_validade_meses=12,
        )
        calibracao.atualizar_validade()
        calibracao.save()
        certificado, _ = CertificadoCalibracao.emitir_para(calibracao)
        detalhe = self.client.get(
            reverse("servicos:detalhe_instrumento", args=[self.instrumento.pk])
        )
        self.assertContains(detalhe, ordem.numero)
        self.assertContains(detalhe, calibracao.numero)
        self.assertContains(detalhe, certificado.numero)
        self.assertContains(detalhe, "Histórico do instrumento")
        cliente = self.client.get(
            reverse("clientes:detalhe_cliente", args=[self.cliente.pk])
        )
        self.assertContains(cliente, ordem.numero)
        self.assertContains(cliente, reverse("servicos:lista_calibracoes") + f"?cliente={self.cliente.pk}")
        self.assertContains(cliente, reverse("servicos:lista_certificados") + f"?cliente={self.cliente.pk}")

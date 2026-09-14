from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, Permission, User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from acesso.models import RegistroAuditoria
from acesso.reset_simulacao import MODELOS_NEGOCIO, ordem_exclusao
from clientes.models import Cliente
from servicos.models import (
    Calibracao,
    CertificadoCalibracao,
    Cobranca,
    ExecucaoValvula,
    Instrumento,
    ItemOrcamento,
    ItemOrdemServico,
    Orcamento,
    OrdemServico,
    Pagamento,
    PontoCalibracao,
    RelatorioTecnico,
    ResultadoCalibracao,
    ServicoSolicitado,
    StatusCalibracao,
    TipoEquipamento,
    TipoInstrumento,
    UnidadePressao,
    Valvula,
    ValvulaRelatorio,
)


class ResetSimulacaoTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="operador-sim",
            email="operador-sim@example.com",
            password="senha-segura-123",
        )
        self.grupo = Group.objects.create(name="GRUPO-SIM")
        self.user.groups.add(self.grupo)
        self.cliente = Cliente.objects.create(
            nome="Cliente Reset",
            cnpj="11.222.333/0001-81",
            cep="17512-400",
            endereco="Rua A, 1",
        )
        self.valvula = Valvula.objects.create(
            cliente=self.cliente,
            codigo="VAL-RST",
        )
        self.instrumento = Instrumento.objects.create(
            cliente=self.cliente,
            codigo="MAN-RST",
            tipo=TipoInstrumento.MANOMETRO,
            faixa_minima=Decimal("0"),
            faixa_maxima=Decimal("10"),
            unidade=UnidadePressao.BAR,
        )
        self.ordem = OrdemServico.criar(
            cliente=self.cliente,
            data_entrada=date(2026, 9, 13),
        )
        self.item_val = ItemOrdemServico.objects.create(
            ordem_servico=self.ordem,
            tipo_equipamento=TipoEquipamento.VALVULA,
            valvula=self.valvula,
            servico_solicitado=ServicoSolicitado.MANUTENCAO,
        )
        self.item_man = ItemOrdemServico.objects.create(
            ordem_servico=self.ordem,
            tipo_equipamento=TipoEquipamento.INSTRUMENTO,
            instrumento=self.instrumento,
            servico_solicitado=ServicoSolicitado.CALIBRACAO,
        )
        self.calibracao = Calibracao.objects.create(
            instrumento=self.instrumento,
            item_ordem_servico=self.item_man,
            data_calibracao=date(2026, 9, 13),
            criterio_aceitacao="Interno",
            tolerancia=Decimal("0.10"),
            status=StatusCalibracao.CONCLUIDA,
            resultado=ResultadoCalibracao.APROVADO,
        )
        PontoCalibracao.objects.create(
            calibracao=self.calibracao,
            ordem=1,
            valor_referencia=Decimal("1"),
            indicacao_instrumento=Decimal("1"),
        )
        CertificadoCalibracao.objects.create(
            calibracao=self.calibracao,
            numero="CERT-999999",
            emitido_em=timezone.now(),
        )
        ExecucaoValvula.abrir_para_item(self.item_val, self.user)
        self.orcamento = Orcamento.objects.create(
            cliente=self.cliente,
            data_emissao=date(2026, 9, 13),
        )
        ItemOrcamento.objects.create(
            orcamento=self.orcamento,
            servico=ServicoSolicitado.CALIBRACAO,
            descricao="Calibração",
            quantidade=1,
            valor_unitario=Decimal("10.00"),
            total=Decimal("10.00"),
        )
        self.relatorio = RelatorioTecnico.objects.create(
            cliente=self.cliente,
            numero_relatorio="RAT-RST",
            setor="Teste",
        )
        ValvulaRelatorio.objects.create(
            relatorio=self.relatorio,
            valvula=self.valvula,
            item=1,
        )
        RegistroAuditoria.objects.create(
            usuario=self.user,
            acao="TESTE",
            modelo="Cliente",
            objeto_id=str(self.cliente.pk),
        )
        self.user_id = self.user.pk
        self.username = self.user.username
        self.password_hash = self.user.password
        self.grupo_id = self.grupo.pk
        self.permissoes = Permission.objects.count()

    def test_ordem_exclusao_respeita_fk_protect(self):
        ordem = ordem_exclusao()
        self.assertLess(ordem.index(Pagamento), ordem.index(Cobranca))
        self.assertLess(ordem.index(ExecucaoValvula), ordem.index(ItemOrdemServico))
        self.assertLess(ordem.index(CertificadoCalibracao), ordem.index(Calibracao))
        self.assertLess(ordem.index(PontoCalibracao), ordem.index(Calibracao))
        self.assertLess(ordem.index(ItemOrdemServico), ordem.index(OrdemServico))
        self.assertLess(ordem.index(Valvula), ordem.index(Cliente))
        self.assertLess(ordem.index(Instrumento), ordem.index(Cliente))

    def test_reset_preserva_usuario_e_apaga_negocio(self):
        with override_settings(DEBUG=True):
            call_command("reset_simulacao", confirmar="RESETAR")
        self.assertTrue(
            User.objects.filter(pk=self.user_id, username=self.username).exists()
        )
        user = User.objects.get(pk=self.user_id)
        self.assertEqual(user.password, self.password_hash)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.groups.filter(pk=self.grupo_id).exists())
        self.assertEqual(Permission.objects.count(), self.permissoes)
        self.assertEqual(Cliente.objects.count(), 0)
        self.assertEqual(Valvula.objects.count(), 0)
        self.assertEqual(Instrumento.objects.count(), 0)
        self.assertEqual(OrdemServico.objects.count(), 0)
        self.assertEqual(ItemOrdemServico.objects.count(), 0)
        self.assertEqual(Calibracao.objects.count(), 0)
        self.assertEqual(ExecucaoValvula.objects.count(), 0)
        self.assertEqual(CertificadoCalibracao.objects.count(), 0)
        self.assertEqual(Orcamento.objects.count(), 0)
        self.assertEqual(RelatorioTecnico.objects.count(), 0)
        self.assertEqual(RegistroAuditoria.objects.count(), 0)
        for modelo in MODELOS_NEGOCIO:
            self.assertEqual(modelo.objects.count(), 0, modelo._meta.label)

    def test_sem_confirmacao_nao_apaga(self):
        with self.assertRaises(CommandError):
            call_command("reset_simulacao")
        self.assertTrue(Cliente.objects.filter(pk=self.cliente.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.user_id).exists())

    def test_confirmacao_errada_nao_apaga(self):
        with self.assertRaises(CommandError):
            call_command("reset_simulacao", confirmar="sim")
        self.assertTrue(Cliente.objects.filter(pk=self.cliente.pk).exists())

    @override_settings(DEBUG=False)
    def test_bloqueado_em_producao(self):
        with self.assertRaises(CommandError):
            call_command("reset_simulacao", confirmar="RESETAR")
        self.assertTrue(Cliente.objects.filter(pk=self.cliente.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.user_id).exists())

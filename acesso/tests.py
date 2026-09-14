from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from acesso.models import RegistroAuditoria
from acesso.permissoes import (
    GRUPO_ADMINISTRADOR,
    GRUPO_COMERCIAL,
    GRUPO_CONSULTA,
    GRUPO_FINANCEIRO,
    GRUPO_TECNICO,
)
from clientes.models import Cliente
from servicos.models import (
    Calibracao,
    CertificadoCalibracao,
    Cobranca,
    FormaPagamento,
    Instrumento,
    ItemOrcamento,
    Orcamento,
    PontoCalibracao,
    ServicoSolicitado,
    TipoInstrumento,
    UnidadePressao,
)


class PermissoesAcessoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_permissoes")
        cls.hoje = timezone.localdate()
        cls.cliente = Cliente.objects.create(
            nome="Empresa Perm",
            cnpj="11.222.333/0001-81",
            cep="17512-400",
            endereco="Rua A, 1",
        )
        cls.instrumento = Instrumento.objects.create(
            cliente=cls.cliente,
            codigo="MAN-PERM",
            tipo=TipoInstrumento.MANOMETRO,
            faixa_minima=Decimal("0"),
            faixa_maxima=Decimal("10"),
            unidade=UnidadePressao.BAR,
        )
        cls.cobranca = Cobranca.criar(
            cliente=cls.cliente,
            descricao="Cobrança de permissão",
            valor_original=Decimal("100.00"),
            data_emissao=cls.hoje,
            data_vencimento=cls.hoje + timedelta(days=5),
        )
        cls.senha = "senha-segura-123"
        cls.superuser = User.objects.create_superuser(
            "admin", "admin@example.com", cls.senha
        )

    def _usuario(self, username, grupo):
        user = User.objects.create_user(username, f"{username}@ex.com", self.senha)
        user.groups.add(Group.objects.get(name=grupo))
        return user

    def _login(self, user):
        self.client.login(username=user.username, password=self.senha)

    def test_seed_idempotente_e_grupos(self):
        call_command("seed_permissoes")
        nomes = set(Group.objects.filter(name__in=[
            GRUPO_ADMINISTRADOR,
            GRUPO_TECNICO,
            GRUPO_COMERCIAL,
            GRUPO_FINANCEIRO,
            GRUPO_CONSULTA,
        ]).values_list("name", flat=True))
        self.assertEqual(len(nomes), 5)
        tecnico = Group.objects.get(name=GRUPO_TECNICO)
        self.assertTrue(tecnico.permissions.filter(codename="concluir_calibracao").exists())
        self.assertFalse(tecnico.permissions.filter(codename="registrar_pagamento").exists())
        financeiro = Group.objects.get(name=GRUPO_FINANCEIRO)
        self.assertTrue(financeiro.permissions.filter(codename="registrar_pagamento").exists())
        self.assertFalse(financeiro.permissions.filter(codename="emitir_certificado").exists())

    def test_anonimo_vai_para_login(self):
        response = self.client.get(reverse("acesso:lista_usuarios"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_superusuario_acessa_tudo(self):
        self._login(self.superuser)
        self.assertEqual(self.client.get(reverse("acesso:lista_usuarios")).status_code, 200)
        self.assertEqual(self.client.get(reverse("acesso:lista_auditoria")).status_code, 200)
        self.assertEqual(self.client.get(reverse("servicos:lista_cobrancas")).status_code, 200)
        self.assertEqual(self.client.get(reverse("servicos:lista_calibracoes")).status_code, 200)

    def test_consulta_ve_e_nao_altera(self):
        user = self._usuario("consulta", GRUPO_CONSULTA)
        self._login(user)
        self.assertEqual(self.client.get(reverse("servicos:lista_cobrancas")).status_code, 200)
        self.assertEqual(self.client.get(reverse("clientes:lista_clientes")).status_code, 200)
        pagar = self.client.post(
            reverse("servicos:registrar_pagamento", args=[self.cobranca.pk]),
            {
                "data_pagamento": self.hoje.isoformat(),
                "valor": "10.00",
                "forma_pagamento": FormaPagamento.PIX,
            },
        )
        self.assertEqual(pagar.status_code, 403)
        self.assertEqual(self.client.get(reverse("acesso:lista_usuarios")).status_code, 403)
        self.assertEqual(self.client.get(reverse("acesso:lista_auditoria")).status_code, 403)

    def test_tecnico_bloqueado_no_financeiro_e_usuarios(self):
        user = self._usuario("tecnico", GRUPO_TECNICO)
        self._login(user)
        self.assertEqual(self.client.get(reverse("servicos:lista_calibracoes")).status_code, 200)
        self.assertEqual(self.client.get(reverse("servicos:lista_cobrancas")).status_code, 403)
        self.assertEqual(
            self.client.post(
                reverse("servicos:registrar_pagamento", args=[self.cobranca.pk]),
                {
                    "data_pagamento": self.hoje.isoformat(),
                    "valor": "10.00",
                    "forma_pagamento": FormaPagamento.PIX,
                },
            ).status_code,
            403,
        )
        self.assertEqual(self.client.get(reverse("acesso:lista_usuarios")).status_code, 403)

    def test_comercial_bloqueado_em_pagamento_e_certificado(self):
        user = self._usuario("comercial", GRUPO_COMERCIAL)
        self._login(user)
        self.assertEqual(self.client.get(reverse("servicos:lista_orcamentos")).status_code, 200)
        self.assertEqual(self.client.get(reverse("clientes:cadastrar_cliente")).status_code, 200)
        self.assertEqual(
            self.client.post(
                reverse("servicos:registrar_pagamento", args=[self.cobranca.pk]),
                {
                    "data_pagamento": self.hoje.isoformat(),
                    "valor": "10.00",
                    "forma_pagamento": FormaPagamento.PIX,
                },
            ).status_code,
            403,
        )
        self.assertEqual(self.client.get(reverse("servicos:lista_calibracoes")).status_code, 403)

    def test_financeiro_acessa_pagamento_e_bloqueia_tecnico(self):
        cobranca = Cobranca.criar(
            cliente=self.cliente,
            descricao="Cobrança financeira",
            valor_original=Decimal("100.00"),
            data_emissao=self.hoje,
            data_vencimento=self.hoje + timedelta(days=5),
        )
        user = self._usuario("financeiro", GRUPO_FINANCEIRO)
        self._login(user)
        self.assertEqual(self.client.get(reverse("servicos:lista_cobrancas")).status_code, 200)
        self.assertEqual(self.client.get(reverse("servicos:cadastrar_calibracao")).status_code, 403)
        pagar = self.client.post(
            reverse("servicos:registrar_pagamento", args=[cobranca.pk]),
            {
                "data_pagamento": self.hoje.isoformat(),
                "valor": "40.00",
                "forma_pagamento": FormaPagamento.PIX,
            },
        )
        self.assertEqual(pagar.status_code, 302)
        cobranca.refresh_from_db()
        self.assertEqual(cobranca.total_pago(), Decimal("40.00"))
        registro = RegistroAuditoria.objects.get(acao="PAGAMENTO_REGISTRADO")
        self.assertEqual(registro.usuario_id, user.pk)
        self.assertEqual(registro.modelo, "Cobranca")
        self.assertEqual(registro.objeto_id, cobranca.numero)
        self.assertIn("40", registro.descricao)
        self.assertEqual(registro.ip, "127.0.0.1")

    def test_administrador_gerencia_usuarios(self):
        admin = self._usuario("gestor", GRUPO_ADMINISTRADOR)
        self._login(admin)
        self.assertEqual(self.client.get(reverse("acesso:lista_usuarios")).status_code, 200)
        criar = self.client.post(
            reverse("acesso:cadastrar_usuario"),
            {
                "username": "novo.op",
                "first_name": "Novo",
                "email": "novo@ex.com",
                "senha": "SenhaForte123",
                "senha_confirmacao": "SenhaForte123",
                "is_active": "on",
            },
        )
        novo = User.objects.get(username="novo.op")
        self.assertRedirects(criar, reverse("acesso:detalhe_usuario", args=[novo.pk]))
        self.assertTrue(novo.check_password("SenhaForte123"))
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao="USUARIO_CRIADO", objeto_id="novo.op"
            ).exists()
        )

    def test_csrf_e_get_nao_altera_usuario(self):
        self._login(self.superuser)
        alvo = User.objects.create_user("alvo", "alvo@ex.com", self.senha)
        get_inativar = self.client.get(
            reverse("acesso:inativar_usuario", args=[alvo.pk])
        )
        self.assertEqual(get_inativar.status_code, 405)
        csrf = Client(enforce_csrf_checks=True)
        csrf.login(username="admin", password=self.senha)
        self.assertEqual(
            csrf.post(reverse("acesso:inativar_usuario", args=[alvo.pk])).status_code,
            403,
        )
        alvo.refresh_from_db()
        self.assertTrue(alvo.is_active)

    def test_cancelar_cobranca_gera_auditoria(self):
        self._login(self.superuser)
        self.client.post(reverse("servicos:cancelar_cobranca", args=[self.cobranca.pk]))
        self.cobranca.refresh_from_db()
        self.assertEqual(self.cobranca.status, "cancelado")
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao="COBRANCA_CANCELADA", objeto_id=self.cobranca.numero
            ).exists()
        )


class AuditoriaWorkflowTests(TestCase):
    def setUp(self):
        call_command("seed_permissoes")
        self.senha = "senha-segura-123"
        self.user = User.objects.create_superuser(
            "operador", "operador@example.com", self.senha
        )
        self.client.login(username="operador", password=self.senha)
        self.hoje = timezone.localdate()
        self.cliente = Cliente.objects.create(
            nome="Empresa Workflow",
            cnpj="11.222.333/0001-81",
            cep="17512-400",
            endereco="Rua A, 1",
        )
        self.instrumento = Instrumento.objects.create(
            cliente=self.cliente,
            codigo="MAN-WF",
            tipo=TipoInstrumento.MANOMETRO,
            faixa_minima=Decimal("0"),
            faixa_maxima=Decimal("10"),
            unidade=UnidadePressao.BAR,
        )

    def test_calibracao_certificado_e_orcamento_geram_auditoria(self):
        calibracao = Calibracao.objects.create(
            instrumento=self.instrumento,
            data_calibracao=self.hoje,
            procedimento="PROC-CAL-001",
            padrao_utilizado="Fluke 729",
            criterio_aceitacao="Critério interno",
            tolerancia=Decimal("0.10"),
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
            indicacao_instrumento=Decimal("10.05"),
        )
        calibracao.registrar_execucao(self.user)
        calibracao.registrar_revisao(self.user)
        calibracao.save()
        self.client.post(reverse("servicos:concluir_calibracao", args=[calibracao.pk]))
        calibracao.refresh_from_db()
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao="CALIBRACAO_CONCLUIDA",
                modelo="Calibracao",
                objeto_id=calibracao.numero,
            ).exists()
        )
        self.client.post(reverse("servicos:emitir_certificado", args=[calibracao.pk]))
        emitido = RegistroAuditoria.objects.get(acao="CERTIFICADO_EMITIDO")
        self.assertEqual(emitido.usuario_id, self.user.pk)
        self.assertEqual(emitido.modelo, "CertificadoCalibracao")
        certificado = CertificadoCalibracao.objects.get()
        self.assertEqual(emitido.objeto_id, certificado.numero)
        self.client.post(
            reverse("servicos:cancelar_certificado", args=[certificado.pk])
        )
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao="CERTIFICADO_CANCELADO",
                modelo="CertificadoCalibracao",
                objeto_id=certificado.numero,
            ).exists()
        )

        orcamento = Orcamento.criar(cliente=self.cliente, data_emissao=self.hoje)
        item = ItemOrcamento(
            orcamento=orcamento,
            servico=ServicoSolicitado.CALIBRACAO,
            instrumento=self.instrumento,
            descricao="Calibração",
            quantidade=1,
            valor_unitario=Decimal("150.00"),
            desconto=Decimal("0.00"),
            ordem=1,
        )
        item.full_clean()
        item.save()
        self.client.post(reverse("servicos:enviar_orcamento", args=[orcamento.pk]))
        self.client.post(reverse("servicos:aprovar_orcamento", args=[orcamento.pk]))
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao="ORCAMENTO_APROVADO", objeto_id=orcamento.numero
            ).exists()
        )
        self.client.post(reverse("servicos:gerar_os_orcamento", args=[orcamento.pk]))
        self.assertTrue(
            RegistroAuditoria.objects.filter(acao="ORDEM_SERVICO_GERADA").exists()
        )

        consulta = User.objects.create_user("leitura", "leitura@ex.com", self.senha)
        consulta.groups.add(Group.objects.get(name=GRUPO_CONSULTA))
        self.client.login(username="leitura", password=self.senha)
        self.assertEqual(
            self.client.post(
                reverse("servicos:emitir_certificado", args=[calibracao.pk])
            ).status_code,
            403,
        )

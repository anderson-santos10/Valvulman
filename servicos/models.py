from decimal import Decimal
import secrets

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import IntegrityError, models, transaction
from django.db.models import Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from clientes.models import Cliente


def gerar_token_avulso():
    return secrets.token_urlsafe(32)


def identificacao_usuario(user):
    if user is None:
        return ""
    nome = (user.get_full_name() or "").strip()
    return nome or user.get_username()


class UnidadePressao(models.TextChoices):
    PSI = "psi", "psi"
    BAR = "bar", "bar"
    KGF_CM2 = "kgf/cm²", "kgf/cm²"


class Valvula(models.Model):
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name="valvulas",
    )
    codigo = models.CharField(
        max_length=50,
        help_text="Identificação interna no Valvulman. Única por cliente.",
    )
    tag = models.CharField(max_length=100, blank=True)
    numero_serie = models.CharField(max_length=100, blank=True)
    fabricante = models.CharField(max_length=150, blank=True)
    modelo = models.CharField(max_length=150, blank=True)
    diametro_nominal = models.CharField(
        max_length=50,
        blank=True,
        help_text="Diâmetro como informado pelo cliente (ex.: 1\", DN 25).",
    )
    pressao_ajuste = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        blank=True,
        null=True,
    )
    unidade_pressao = models.CharField(
        max_length=10,
        choices=UnidadePressao.choices,
        default=UnidadePressao.PSI,
        blank=True,
    )
    observacoes = models.TextField(blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Válvula"
        verbose_name_plural = "Válvulas"
        ordering = ["cliente__nome", "codigo"]
        constraints = [
            models.UniqueConstraint(
                fields=["cliente", "codigo"],
                name="uniq_valvula_cliente_codigo",
            ),
        ]
        indexes = [
            models.Index(fields=["tag"]),
            models.Index(fields=["numero_serie"]),
        ]

    def __str__(self):
        identificacao = self.tag or self.numero_serie or self.codigo
        return f"{self.codigo} — {identificacao}"

    @property
    def pressao_formatada(self):
        if self.pressao_ajuste in (None, ""):
            return ""
        valor_decimal = self.pressao_ajuste
        if not isinstance(valor_decimal, Decimal):
            valor_decimal = Decimal(str(valor_decimal))
        unidade = self.unidade_pressao or UnidadePressao.PSI
        valor = format(valor_decimal, "f").rstrip("0").rstrip(".")
        return f"{valor} {unidade}"


class TipoInstrumento(models.TextChoices):
    MANOMETRO = "manometro", "Manômetro"


class TipoEquipamento(models.TextChoices):
    INSTRUMENTO = "instrumento", "Manômetro"
    VALVULA = "valvula", "Válvula"


class Instrumento(models.Model):
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name="instrumentos",
    )
    codigo = models.CharField(
        max_length=50,
        help_text="Identificação interna no Valvulman. Única por cliente.",
    )
    tag = models.CharField(max_length=100, blank=True)
    numero_serie = models.CharField(max_length=100, blank=True)
    tipo = models.CharField(
        max_length=20,
        choices=TipoInstrumento.choices,
        default=TipoInstrumento.MANOMETRO,
    )
    fabricante = models.CharField(max_length=150, blank=True)
    modelo = models.CharField(max_length=150, blank=True)
    faixa_minima = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        blank=True,
        null=True,
    )
    faixa_maxima = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        blank=True,
        null=True,
    )
    unidade = models.CharField(
        max_length=10,
        choices=UnidadePressao.choices,
        default=UnidadePressao.PSI,
        blank=True,
    )
    resolucao = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        blank=True,
        null=True,
        help_text="Menor divisão da escala, na mesma unidade da faixa.",
    )
    observacoes = models.TextField(blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Instrumento"
        verbose_name_plural = "Instrumentos"
        ordering = ["cliente__nome", "codigo"]
        constraints = [
            models.UniqueConstraint(
                fields=["cliente", "codigo"],
                name="uniq_instrumento_cliente_codigo",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(faixa_minima__isnull=True)
                    | models.Q(faixa_maxima__isnull=True)
                    | models.Q(faixa_minima__lte=models.F("faixa_maxima"))
                ),
                name="instrumento_faixa_min_lte_max",
            ),
        ]
        indexes = [
            models.Index(fields=["tag"]),
            models.Index(fields=["numero_serie"]),
            models.Index(fields=["tipo"]),
        ]

    def __str__(self):
        identificacao = self.tag or self.numero_serie or self.codigo
        return f"{self.codigo} — {identificacao}"

    @staticmethod
    def _formatar_decimal(valor):
        if valor in (None, ""):
            return ""
        valor_decimal = valor
        if not isinstance(valor_decimal, Decimal):
            valor_decimal = Decimal(str(valor_decimal))
        texto = format(valor_decimal, "f")
        if "." in texto:
            texto = texto.rstrip("0").rstrip(".")
        return texto

    @property
    def faixa_formatada(self):
        minimo = self._formatar_decimal(self.faixa_minima)
        maximo = self._formatar_decimal(self.faixa_maxima)
        if not minimo and not maximo:
            return ""
        unidade = self.unidade or UnidadePressao.PSI
        return f"{minimo or '—'} a {maximo or '—'} {unidade}"

    @property
    def resolucao_formatada(self):
        valor = self._formatar_decimal(self.resolucao)
        if not valor:
            return ""
        unidade = self.unidade or UnidadePressao.PSI
        return f"{valor} {unidade}"

    def ultima_calibracao(self):
        calibracoes = getattr(self, "_prefetched_objects_cache", {}).get("calibracoes")
        if calibracoes is not None:
            validas = [
                calibracao
                for calibracao in calibracoes
                if calibracao.status != StatusCalibracao.CANCELADA
            ]
            if not validas:
                return None
            return sorted(
                validas,
                key=lambda calibracao: (calibracao.data_calibracao, calibracao.pk),
                reverse=True,
            )[0]
        return (
            self.calibracoes.exclude(status=StatusCalibracao.CANCELADA)
            .order_by("-data_calibracao", "-pk")
            .first()
        )

    def situacao_calibracao(self):
        calibracao = self.ultima_calibracao()
        if calibracao is None:
            return "sem_calibracao", "Sem calibração"
        if not calibracao.data_validade:
            return "sem_validade", "Sem validade documental"
        if calibracao.validade_expirada:
            return "vencida", "Calibração vencida"
        return "valida", "Calibração válida"

    @property
    def situacao_calibracao_codigo(self):
        return self.situacao_calibracao()[0]

    @property
    def situacao_calibracao_rotulo(self):
        return self.situacao_calibracao()[1]


class PadraoMedicao(models.Model):
    codigo = models.CharField(
        max_length=50,
        unique=True,
        help_text="Identificação interna do padrão no laboratório. Única.",
    )
    identificacao = models.CharField(max_length=255)
    tipo = models.CharField(max_length=100, blank=True)
    fabricante = models.CharField(max_length=150, blank=True)
    modelo = models.CharField(max_length=150, blank=True)
    numero_serie = models.CharField(max_length=100, blank=True)
    faixa_minima = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        blank=True,
        null=True,
    )
    faixa_maxima = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        blank=True,
        null=True,
    )
    unidade = models.CharField(
        max_length=10,
        choices=UnidadePressao.choices,
        default=UnidadePressao.PSI,
        blank=True,
    )
    resolucao = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        blank=True,
        null=True,
        help_text="Menor divisão da escala, na mesma unidade da faixa.",
    )
    numero_certificado = models.CharField(
        max_length=100,
        blank=True,
        help_text="Número do certificado de calibração do próprio padrão.",
    )
    data_calibracao = models.DateField(
        null=True,
        blank=True,
        help_text="Data em que o padrão foi calibrado.",
    )
    data_validade = models.DateField(
        null=True,
        blank=True,
        help_text="Validade documental do certificado do padrão. Sem data, o uso não afirma prazo.",
    )
    observacoes = models.TextField(blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Padrão de medição"
        verbose_name_plural = "Padrões de medição"
        ordering = ["codigo"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(faixa_minima__isnull=True)
                    | models.Q(faixa_maxima__isnull=True)
                    | models.Q(faixa_minima__lte=models.F("faixa_maxima"))
                ),
                name="padrao_medicao_faixa_min_lte_max",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(resolucao__isnull=True)
                    | models.Q(resolucao__gte=0)
                ),
                name="padrao_medicao_resolucao_nao_negativa",
            ),
        ]
        indexes = [
            models.Index(fields=["numero_serie"]),
            models.Index(fields=["fabricante"]),
            models.Index(fields=["ativo"]),
            models.Index(fields=["data_validade"]),
        ]

    def __str__(self):
        return self.rotulo_selecao()

    def save(self, *args, **kwargs):
        if not (self.codigo or "").strip():
            self.codigo = self.proximo_codigo()
        else:
            self.codigo = self.codigo.strip()
        super().save(*args, **kwargs)

    @classmethod
    def proximo_codigo(cls):
        existentes = cls.objects.values_list("codigo", flat=True)
        maior = 0
        prefixo = "PAD-"
        for codigo in existentes:
            if not codigo:
                continue
            if codigo.upper().startswith(prefixo) and codigo[4:].isdigit():
                maior = max(maior, int(codigo[4:]))
        return f"{prefixo}{maior + 1:04d}"

    @property
    def faixa_formatada(self):
        minimo = Instrumento._formatar_decimal(self.faixa_minima)
        maximo = Instrumento._formatar_decimal(self.faixa_maxima)
        if not minimo and not maximo:
            return ""
        unidade = self.unidade or UnidadePressao.PSI
        return f"{minimo or '—'} a {maximo or '—'} {unidade}"

    @property
    def resolucao_formatada(self):
        valor = Instrumento._formatar_decimal(self.resolucao)
        if not valor:
            return ""
        unidade = self.unidade or UnidadePressao.PSI
        return f"{valor} {unidade}"

    def vigencia_em(self, referencia=None):
        if not self.data_validade:
            return "sem_validade"
        data = referencia or timezone.localdate()
        if data > self.data_validade:
            return "vencido"
        return "vigente"

    @property
    def situacao_validade(self):
        return self.vigencia_em()

    @property
    def situacao_validade_display(self):
        rotulos = {
            "vigente": "Vigente",
            "vencido": "Vencido",
            "sem_validade": "Sem validade cadastrada",
        }
        return rotulos[self.situacao_validade]

    def rotulo_selecao(self):
        partes = [self.codigo]
        if self.identificacao:
            partes.append(self.identificacao)
        equipamento = " ".join(
            parte for parte in (self.fabricante, self.modelo) if parte
        )
        if equipamento:
            partes.append(equipamento)
        if self.numero_serie:
            partes.append(f"SN {self.numero_serie}")
        return " — ".join(partes)

    def rotulo_documento(self):
        titulo = " — ".join(
            parte for parte in (self.codigo, self.identificacao) if parte
        )
        linhas = [titulo]
        if self.fabricante:
            linhas.append(f"Fabricante: {self.fabricante}")
        if self.modelo:
            linhas.append(f"Modelo: {self.modelo}")
        if self.numero_serie:
            linhas.append(f"Nº série: {self.numero_serie}")
        if self.numero_certificado:
            linhas.append(f"Certificado: {self.numero_certificado}")
        return "\n".join(linhas)

    def validar_uso(self, data, permitir_inativo=False):
        if not self.ativo and not permitir_inativo:
            return (
                "Este padrão está inativo e não pode ser selecionado "
                "para nova calibração."
            )
        if self.data_validade and data and data > self.data_validade:
            validade = self.data_validade.strftime("%d/%m/%Y")
            return (
                f"O padrão {self.codigo} estava vencido na data da calibração "
                f"(válido até {validade})."
            )
        return ""


class StatusCalibracao(models.TextChoices):
    RASCUNHO = "rascunho", "Rascunho"
    CONCLUIDA = "concluida", "Concluída"
    CANCELADA = "cancelada", "Cancelada"


class ResultadoCalibracao(models.TextChoices):
    PENDENTE = "pendente", "Pendente"
    APROVADO = "aprovado", "Aprovado"
    REPROVADO = "reprovado", "Reprovado"


class StatusExecucaoValvula(models.TextChoices):
    RASCUNHO = "rascunho", "Rascunho"
    CONCLUIDA = "concluida", "Concluída"
    CANCELADA = "cancelada", "Cancelada"


class ResultadoExecucaoValvula(models.TextChoices):
    PENDENTE = "pendente", "Pendente"
    APROVADO = "aprovado", "Aprovado"
    REPROVADO = "reprovado", "Reprovado"


class StatusOrdemServico(models.TextChoices):
    ABERTA = "aberta", "Aberta"
    RECEBIDA = "recebida", "Recebida"
    EM_EXECUCAO = "em_execucao", "Em execução"
    AGUARDANDO_REVISAO = "aguardando_revisao", "Aguardando revisão"
    CONCLUIDA = "concluida", "Concluída"
    ENTREGUE = "entregue", "Entregue"
    CANCELADA = "cancelada", "Cancelada"


class ServicoSolicitado(models.TextChoices):
    CALIBRACAO = "calibracao", "Calibração"
    ENSAIO = "ensaio", "Ensaio"
    AJUSTE = "ajuste", "Ajuste"
    INSPECAO = "inspecao", "Inspeção"
    MANUTENCAO = "manutencao", "Manutenção"
    OUTRO = "outro", "Outro"


SUGESTOES_CONDICAO_RECEBIMENTO = (
    "Bom estado",
    "Com riscos",
    "Com corrosão",
    "Danificado",
    "Incompleto",
    "Sem identificação",
    "Outro",
)


class StatusItemOrdem(models.TextChoices):
    RECEBIDO = "recebido", "Recebido"
    EM_EXECUCAO = "em_execucao", "Em execução"
    AGUARDANDO_REVISAO = "aguardando_revisao", "Aguardando revisão"
    CONCLUIDO = "concluido", "Concluído"
    DEVOLVIDO = "devolvido", "Devolvido"
    CANCELADO = "cancelado", "Cancelado"


class OrdemServico(models.Model):
    numero = models.CharField(max_length=50, unique=True, blank=True)
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name="ordens_servico",
    )
    data_entrada = models.DateField()
    data_previsao_entrega = models.DateField(null=True, blank=True)
    data_entrega = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=30,
        choices=StatusOrdemServico.choices,
        default=StatusOrdemServico.ABERTA,
    )
    solicitante = models.CharField(max_length=150, blank=True)
    contato_solicitante = models.CharField(max_length=150, blank=True)
    telefone_solicitante = models.CharField(max_length=30, blank=True)
    email_solicitante = models.EmailField(blank=True)
    responsavel_recebimento = models.CharField(max_length=150, blank=True)
    observacoes = models.TextField(blank=True)
    data_conclusao = models.DateField(null=True, blank=True)
    orcamento = models.ForeignKey(
        "Orcamento",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ordens_servico",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Ordem de serviço"
        verbose_name_plural = "Ordens de serviço"
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["numero"]),
            models.Index(fields=["status"]),
            models.Index(fields=["data_entrada"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["orcamento"],
                condition=models.Q(orcamento__isnull=False),
                name="uniq_ordem_servico_orcamento",
            ),
        ]
        permissions = [
            ("receber_ordem", "Pode receber ordem de serviço"),
            ("iniciar_ordem", "Pode iniciar ordem de serviço"),
            ("revisar_ordem", "Pode enviar ordem de serviço para revisão"),
            ("concluir_ordem", "Pode concluir ordem de serviço"),
            ("entregar_ordem", "Pode entregar ordem de serviço"),
            ("cancelar_ordem", "Pode cancelar ordem de serviço"),
        ]

    def __str__(self):
        return self.numero or "OS"

    def save(self, *args, **kwargs):
        if not (self.numero or "").strip():
            self.numero = self.proximo_numero()
        else:
            self.numero = self.numero.strip()
        super().save(*args, **kwargs)

    @classmethod
    def proximo_numero(cls):
        existentes = cls.objects.values_list("numero", flat=True)
        maior = 0
        prefixo = "OS-"
        for numero in existentes:
            if not numero:
                continue
            if numero.upper().startswith(prefixo) and numero[3:].isdigit():
                maior = max(maior, int(numero[3:]))
        return f"{prefixo}{maior + 1:06d}"

    @classmethod
    def criar(cls, **dados):
        for _ in range(8):
            try:
                with transaction.atomic():
                    list(cls.objects.select_for_update().order_by("pk")[:1])
                    ordem = cls(**dados)
                    if not (ordem.numero or "").strip():
                        ordem.numero = cls.proximo_numero()
                    ordem.save()
                    return ordem
            except IntegrityError:
                continue
        raise IntegrityError("Não foi possível gerar um número único de ordem de serviço.")

    @property
    def pode_editar(self):
        return self.status in (
            StatusOrdemServico.ABERTA,
            StatusOrdemServico.RECEBIDA,
            StatusOrdemServico.EM_EXECUCAO,
        )

    @property
    def pode_cancelar(self):
        return self.status in (
            StatusOrdemServico.ABERTA,
            StatusOrdemServico.RECEBIDA,
            StatusOrdemServico.EM_EXECUCAO,
        )

    @property
    def pode_receber(self):
        return self.status == StatusOrdemServico.ABERTA

    @property
    def pode_iniciar(self):
        if self.status not in (
            StatusOrdemServico.ABERTA,
            StatusOrdemServico.RECEBIDA,
        ):
            return False
        for item in self.itens_ativos():
            if item.status != StatusItemOrdem.RECEBIDO:
                continue
            if item.exige_calibracao or item.eh_valvula:
                return False
        return True

    @property
    def pode_aguardar_revisao(self):
        return self.status == StatusOrdemServico.EM_EXECUCAO

    @property
    def pode_concluir(self):
        return self.status in (
            StatusOrdemServico.RECEBIDA,
            StatusOrdemServico.EM_EXECUCAO,
            StatusOrdemServico.AGUARDANDO_REVISAO,
        )

    @property
    def pode_entregar(self):
        return self.status == StatusOrdemServico.CONCLUIDA

    def transicoes_permitidas(self):
        return {
            StatusOrdemServico.ABERTA: {
                StatusOrdemServico.RECEBIDA,
                StatusOrdemServico.EM_EXECUCAO,
                StatusOrdemServico.CANCELADA,
            },
            StatusOrdemServico.RECEBIDA: {
                StatusOrdemServico.EM_EXECUCAO,
                StatusOrdemServico.CONCLUIDA,
                StatusOrdemServico.CANCELADA,
            },
            StatusOrdemServico.EM_EXECUCAO: {
                StatusOrdemServico.RECEBIDA,
                StatusOrdemServico.AGUARDANDO_REVISAO,
                StatusOrdemServico.CONCLUIDA,
                StatusOrdemServico.CANCELADA,
            },
            StatusOrdemServico.AGUARDANDO_REVISAO: {
                StatusOrdemServico.RECEBIDA,
                StatusOrdemServico.EM_EXECUCAO,
                StatusOrdemServico.CONCLUIDA,
            },
            StatusOrdemServico.CONCLUIDA: {StatusOrdemServico.ENTREGUE},
            StatusOrdemServico.ENTREGUE: set(),
            StatusOrdemServico.CANCELADA: set(),
        }.get(self.status, set())

    def itens_ativos(self):
        return [
            item
            for item in self.itens.all()
            if item.status != StatusItemOrdem.CANCELADO
        ]

    def erros_recebimento(self):
        if not self.itens.exists():
            return ["A ordem de serviço precisa de pelo menos um item para ser recebida."]
        return []

    def erros_conclusao(self):
        erros = []
        itens = list(self.itens.select_related("instrumento", "valvula"))
        if not itens:
            erros.append("A ordem de serviço precisa de pelo menos um item.")
            return erros
        pendentes = []
        for item in itens:
            if item.status == StatusItemOrdem.CANCELADO:
                continue
            if item.status not in (
                StatusItemOrdem.CONCLUIDO,
                StatusItemOrdem.DEVOLVIDO,
            ):
                pendentes.append(item.codigo_equipamento)
                continue
            if item.exige_calibracao:
                calibracao = item.calibracao_atual
                if calibracao is None:
                    erros.append(
                        f"O item {item.codigo_equipamento} não possui calibração vinculada."
                    )
                    continue
                if calibracao.status != StatusCalibracao.CONCLUIDA:
                    erros.append(
                        f"A calibração {calibracao.numero} do item {item.codigo_equipamento} ainda não está concluída."
                    )
                elif calibracao.resultado not in (
                    ResultadoCalibracao.APROVADO,
                    ResultadoCalibracao.REPROVADO,
                ):
                    erros.append(
                        f"A calibração {calibracao.numero} ainda está com resultado pendente."
                    )
                continue
            execucao = item.execucao_valvula_atual
            if execucao is None:
                continue
            if execucao.status != StatusExecucaoValvula.CONCLUIDA:
                erros.append(
                    f"A execução da válvula {item.codigo_equipamento} ainda não está concluída."
                )
            elif execucao.resultado not in (
                ResultadoExecucaoValvula.APROVADO,
                ResultadoExecucaoValvula.REPROVADO,
            ):
                erros.append(
                    f"A execução da válvula {item.codigo_equipamento} ainda está com resultado pendente."
                )
        if pendentes:
            erros.insert(
                0,
                "Existem itens pendentes: " + ", ".join(pendentes) + ".",
            )
        return erros

    def alterar_status(self, novo_status, data_entrega=None):
        if novo_status not in self.transicoes_permitidas():
            return False, "Transição de status não permitida para esta ordem de serviço."
        if novo_status == StatusOrdemServico.RECEBIDA:
            erros = self.erros_recebimento()
            if erros:
                return False, erros[0]
        if novo_status == StatusOrdemServico.CONCLUIDA:
            erros = self.erros_conclusao()
            if erros:
                return False, erros[0]
        campos = ["status", "atualizado_em"]
        self.status = novo_status
        if novo_status == StatusOrdemServico.CONCLUIDA:
            self.data_conclusao = timezone.localdate()
            campos.append("data_conclusao")
        if novo_status == StatusOrdemServico.ENTREGUE:
            self.data_entrega = data_entrega or timezone.localdate()
            campos.append("data_entrega")
        self.save(update_fields=campos)
        return True, ""

    def status_derivado_dos_itens(self):
        ativos = self.itens_ativos()
        if not ativos:
            return StatusOrdemServico.ABERTA
        statuses = {item.status for item in ativos}
        finais = {StatusItemOrdem.CONCLUIDO, StatusItemOrdem.DEVOLVIDO}
        revisao = {StatusItemOrdem.AGUARDANDO_REVISAO, *finais}
        if statuses <= finais:
            return StatusOrdemServico.CONCLUIDA
        if statuses <= revisao:
            return StatusOrdemServico.AGUARDANDO_REVISAO
        if statuses & {
            StatusItemOrdem.EM_EXECUCAO,
            StatusItemOrdem.AGUARDANDO_REVISAO,
            StatusItemOrdem.CONCLUIDO,
            StatusItemOrdem.DEVOLVIDO,
        }:
            return StatusOrdemServico.EM_EXECUCAO
        return StatusOrdemServico.RECEBIDA

    def sincronizar_status_pelos_itens(self):
        if self.status in (
            StatusOrdemServico.ENTREGUE,
            StatusOrdemServico.CANCELADA,
        ):
            return False, ""
        destino = self.status_derivado_dos_itens()
        if destino == self.status:
            return True, ""
        if destino not in self.transicoes_permitidas():
            return False, ""
        if destino == StatusOrdemServico.CONCLUIDA and self.erros_conclusao():
            if StatusOrdemServico.EM_EXECUCAO in self.transicoes_permitidas():
                return self.alterar_status(StatusOrdemServico.EM_EXECUCAO)
            return False, ""
        return self.alterar_status(destino)

    @property
    def esta_atrasada(self):
        if self.status in (
            StatusOrdemServico.ENTREGUE,
            StatusOrdemServico.CANCELADA,
        ):
            return False
        if not self.data_previsao_entrega:
            return False
        return self.data_previsao_entrega < timezone.localdate()

    @property
    def situacao_prazo(self):
        if self.status == StatusOrdemServico.ENTREGUE:
            return "entregue", "Entregue"
        if self.status == StatusOrdemServico.CANCELADA:
            return "cancelada", "Cancelada"
        if self.esta_atrasada:
            return "atrasada", "Atrasada"
        if not self.data_previsao_entrega:
            return "sem_previsao", "Sem previsão"
        return "no_prazo", "No prazo"

    def resumo_progresso(self):
        itens = [
            item
            for item in self.itens.all()
            if item.status != StatusItemOrdem.CANCELADO
        ]
        total = len(itens)
        concluidos = sum(
            1 for item in itens if item.status == StatusItemOrdem.CONCLUIDO
        )
        em_execucao = sum(
            1 for item in itens if item.status == StatusItemOrdem.EM_EXECUCAO
        )
        aguardando_revisao = sum(
            1
            for item in itens
            if item.status == StatusItemOrdem.AGUARDANDO_REVISAO
        )
        percentual = int((concluidos * 100) / total) if total else 0
        manometros = sum(1 for item in itens if item.eh_instrumento)
        valvulas = sum(1 for item in itens if item.eh_valvula)
        servicos = {}
        for item in itens:
            chave = item.servico_solicitado
            servicos[chave] = servicos.get(chave, 0) + 1
        return {
            "total": total,
            "concluidos": concluidos,
            "em_execucao": em_execucao,
            "aguardando_revisao": aguardando_revisao,
            "percentual": percentual,
            "manometros": manometros,
            "valvulas": valvulas,
            "servicos": servicos,
        }

    def proximo_passo(self):
        if self.status == StatusOrdemServico.CANCELADA:
            return "Esta ordem foi cancelada."
        if self.status == StatusOrdemServico.ENTREGUE:
            return "Ordem entregue ao cliente."
        if self.status == StatusOrdemServico.CONCLUIDA:
            return "Marcar a ordem como entregue."
        if self.status == StatusOrdemServico.ABERTA:
            if not self.itens.exists():
                return "Inclua os equipamentos recebidos."
            return "Receber a ordem de serviço."
        ativos = self.itens_ativos()
        for item in ativos:
            if item.status == StatusItemOrdem.EM_EXECUCAO:
                return f"Continuar execução de {item.codigo_equipamento}."
        for item in ativos:
            if item.status == StatusItemOrdem.AGUARDANDO_REVISAO:
                if item.eh_valvula:
                    return f"Revisar execução de {item.codigo_equipamento}."
                return f"Revisar o item {item.codigo_equipamento}."
        for item in ativos:
            if item.status == StatusItemOrdem.RECEBIDO:
                if item.eh_valvula:
                    return f"Abrir execução de {item.codigo_equipamento}."
                return f"Iniciar o serviço de {item.codigo_equipamento}."
        if self.status == StatusOrdemServico.AGUARDANDO_REVISAO:
            return "Concluir a ordem após a revisão dos itens."
        return "Acompanhar os itens desta ordem."


class ItemOrdemServico(models.Model):
    ordem_servico = models.ForeignKey(
        OrdemServico,
        on_delete=models.PROTECT,
        related_name="itens",
    )
    tipo_equipamento = models.CharField(
        max_length=20,
        choices=TipoEquipamento.choices,
        default=TipoEquipamento.INSTRUMENTO,
    )
    instrumento = models.ForeignKey(
        Instrumento,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="itens_ordem_servico",
    )
    valvula = models.ForeignKey(
        "Valvula",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="itens_ordem_servico",
    )
    servico_solicitado = models.CharField(
        max_length=20,
        choices=ServicoSolicitado.choices,
        default=ServicoSolicitado.CALIBRACAO,
    )
    condicao_recebimento = models.CharField(max_length=255, blank=True)
    observacoes_recebimento = models.TextField(blank=True)
    status = models.CharField(
        max_length=30,
        choices=StatusItemOrdem.choices,
        default=StatusItemOrdem.RECEBIDO,
    )
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Item da ordem de serviço"
        verbose_name_plural = "Itens da ordem de serviço"
        ordering = ["pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["ordem_servico", "instrumento"],
                condition=models.Q(instrumento__isnull=False),
                name="uniq_item_os_instrumento",
            ),
            models.UniqueConstraint(
                fields=["ordem_servico", "valvula"],
                condition=models.Q(valvula__isnull=False),
                name="uniq_item_os_valvula",
            ),
            models.CheckConstraint(
                condition=(
                    (
                        models.Q(tipo_equipamento=TipoEquipamento.INSTRUMENTO)
                        & models.Q(instrumento__isnull=False)
                        & models.Q(valvula__isnull=True)
                    )
                    | (
                        models.Q(tipo_equipamento=TipoEquipamento.VALVULA)
                        & models.Q(valvula__isnull=False)
                        & models.Q(instrumento__isnull=True)
                    )
                ),
                name="item_os_um_equipamento",
            ),
        ]

    def __str__(self):
        return f"{self.ordem_servico.numero} — {self.codigo_equipamento}"

    def save(self, *args, **kwargs):
        if self.instrumento_id and not self.valvula_id:
            self.tipo_equipamento = TipoEquipamento.INSTRUMENTO
        elif self.valvula_id and not self.instrumento_id:
            self.tipo_equipamento = TipoEquipamento.VALVULA
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.instrumento_id and self.valvula_id:
            raise ValidationError(
                "O item deve apontar para um manômetro ou para uma válvula, nunca para os dois."
            )
        if not self.instrumento_id and not self.valvula_id:
            raise ValidationError("Informe o equipamento deste item.")
        if self.instrumento_id:
            self.tipo_equipamento = TipoEquipamento.INSTRUMENTO
        elif self.valvula_id:
            self.tipo_equipamento = TipoEquipamento.VALVULA
        if self.ordem_servico_id:
            cliente_id = self.ordem_servico.cliente_id
            if self.instrumento_id and self.instrumento.cliente_id != cliente_id:
                raise ValidationError(
                    {
                        "instrumento": "O instrumento deve pertencer ao mesmo cliente da ordem de serviço."
                    }
                )
            if self.valvula_id and self.valvula.cliente_id != cliente_id:
                raise ValidationError(
                    {
                        "valvula": "A válvula deve pertencer ao mesmo cliente da ordem de serviço."
                    }
                )

    @property
    def eh_instrumento(self):
        return self.tipo_equipamento == TipoEquipamento.INSTRUMENTO

    @property
    def eh_valvula(self):
        return self.tipo_equipamento == TipoEquipamento.VALVULA

    @property
    def equipamento(self):
        if self.eh_instrumento:
            return self.instrumento
        return self.valvula

    @property
    def codigo_equipamento(self):
        equipamento = self.equipamento
        if equipamento is None:
            return "—"
        return equipamento.codigo

    @property
    def tag_equipamento(self):
        equipamento = self.equipamento
        return getattr(equipamento, "tag", "") or ""

    @property
    def serie_equipamento(self):
        equipamento = self.equipamento
        return getattr(equipamento, "numero_serie", "") or ""

    @property
    def exige_calibracao(self):
        return self.eh_instrumento and self.servico_solicitado == ServicoSolicitado.CALIBRACAO

    @property
    def calibracao_atual(self):
        return self.calibracoes.order_by("-criado_em").first()

    @property
    def certificado_atual(self):
        calibracao = self.calibracao_atual
        if calibracao is None:
            return None
        return calibracao.certificado_atual

    @property
    def pode_iniciar_calibracao(self):
        if not self.exige_calibracao:
            return False
        if self.ordem_servico.status in (
            StatusOrdemServico.ENTREGUE,
            StatusOrdemServico.CANCELADA,
        ):
            return False
        if self.status in (
            StatusItemOrdem.CONCLUIDO,
            StatusItemOrdem.DEVOLVIDO,
            StatusItemOrdem.CANCELADO,
        ):
            return False
        atual = self.calibracao_atual
        if atual and atual.status != StatusCalibracao.CANCELADA:
            return False
        return self.status in (
            StatusItemOrdem.RECEBIDO,
            StatusItemOrdem.EM_EXECUCAO,
        )

    def aplicar_status(self, novo_status, sincronizar=True):
        self.status = novo_status
        self.save(update_fields=["status", "atualizado_em"])
        if sincronizar and self.ordem_servico_id:
            self.ordem_servico.sincronizar_status_pelos_itens()
        return self

    def sincronizar_com_calibracao(self, calibracao=None):
        if not self.exige_calibracao:
            return self
        calibracao = calibracao or self.calibracao_atual
        if calibracao is None:
            return self
        if calibracao.status == StatusCalibracao.CONCLUIDA:
            destino = StatusItemOrdem.CONCLUIDO
        elif calibracao.esta_revisada:
            destino = StatusItemOrdem.AGUARDANDO_REVISAO
        else:
            destino = StatusItemOrdem.EM_EXECUCAO
        return self.aplicar_status(destino)

    @property
    def execucao_valvula_atual(self):
        if not self.eh_valvula:
            return None
        return getattr(self, "execucao_valvula", None)

    def pode_concluir_item(self):
        if self.exige_calibracao:
            calibracao = self.calibracao_atual
            return (
                calibracao is not None
                and calibracao.status == StatusCalibracao.CONCLUIDA
            )
        if self.eh_valvula:
            execucao = self.execucao_valvula_atual
            return (
                execucao is not None
                and execucao.status == StatusExecucaoValvula.CONCLUIDA
                and execucao.resultado
                in (
                    ResultadoExecucaoValvula.APROVADO,
                    ResultadoExecucaoValvula.REPROVADO,
                )
            )
        return True

    def sincronizar_com_execucao_valvula(self, execucao=None):
        if not self.eh_valvula:
            return self
        execucao = execucao or self.execucao_valvula_atual
        if execucao is None:
            return self
        if execucao.status == StatusExecucaoValvula.CONCLUIDA:
            destino = StatusItemOrdem.CONCLUIDO
        elif execucao.status == StatusExecucaoValvula.CANCELADA:
            return self
        elif execucao.esta_revisada:
            destino = StatusItemOrdem.AGUARDANDO_REVISAO
        else:
            destino = StatusItemOrdem.EM_EXECUCAO
        return self.aplicar_status(destino)


class ExecucaoValvula(models.Model):
    item_ordem_servico = models.OneToOneField(
        ItemOrdemServico,
        on_delete=models.PROTECT,
        related_name="execucao_valvula",
    )
    status = models.CharField(
        max_length=20,
        choices=StatusExecucaoValvula.choices,
        default=StatusExecucaoValvula.RASCUNHO,
    )
    resultado = models.CharField(
        max_length=20,
        choices=ResultadoExecucaoValvula.choices,
        default=ResultadoExecucaoValvula.PENDENTE,
    )
    executor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="execucoes_valvula_executadas",
    )
    executor_nome = models.CharField(max_length=150, blank=True)
    executado_em = models.DateTimeField(null=True, blank=True)
    revisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="execucoes_valvula_revisadas",
    )
    revisor_nome = models.CharField(max_length=150, blank=True)
    revisado_em = models.DateTimeField(null=True, blank=True)
    observacoes_revisao = models.TextField(blank=True)
    data_inicio = models.DateField(null=True, blank=True)
    data_fim = models.DateField(null=True, blank=True)
    descricao_servico = models.TextField(blank=True)
    observacoes = models.TextField(blank=True)
    valvula_codigo = models.CharField(max_length=50, blank=True)
    valvula_tag = models.CharField(max_length=100, blank=True)
    valvula_numero_serie = models.CharField(max_length=100, blank=True)
    valvula_fabricante = models.CharField(max_length=150, blank=True)
    valvula_modelo = models.CharField(max_length=150, blank=True)
    valvula_diametro_nominal = models.CharField(max_length=50, blank=True)
    valvula_pressao_ajuste = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        blank=True,
        null=True,
    )
    valvula_unidade_pressao = models.CharField(max_length=10, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Execução de válvula"
        verbose_name_plural = "Execuções de válvula"
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["resultado"]),
            models.Index(fields=["data_inicio"]),
        ]

    def __str__(self):
        item = self.item_ordem_servico
        return f"{item.ordem_servico.numero} — {item.codigo_equipamento}"

    def save(self, *args, **kwargs):
        criar = self.pk is None
        self.validar_item_valvula()
        if criar:
            self.aplicar_snapshot()
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        self.validar_item_valvula()

    def validar_item_valvula(self):
        item = self.item_ordem_servico
        if item is None:
            raise ValidationError("A execução precisa estar vinculada a um item da OS.")
        if not item.eh_valvula or not item.valvula_id:
            raise ValidationError(
                "A execução de válvula só pode ser criada para um item de válvula da OS."
            )

    def aplicar_snapshot(self):
        valvula = self.item_ordem_servico.valvula
        self.valvula_codigo = valvula.codigo
        self.valvula_tag = valvula.tag or ""
        self.valvula_numero_serie = valvula.numero_serie or ""
        self.valvula_fabricante = valvula.fabricante or ""
        self.valvula_modelo = valvula.modelo or ""
        self.valvula_diametro_nominal = valvula.diametro_nominal or ""
        self.valvula_pressao_ajuste = valvula.pressao_ajuste
        self.valvula_unidade_pressao = valvula.unidade_pressao or ""
        return self

    @classmethod
    def abrir_para_item(cls, item, user):
        if not item.eh_valvula or not item.valvula_id:
            raise ValidationError(
                "A execução de válvula só pode ser aberta para um item de válvula."
            )
        existente = getattr(item, "execucao_valvula", None)
        if existente is not None:
            if item.status == StatusItemOrdem.RECEBIDO:
                item.sincronizar_com_execucao_valvula(existente)
            return existente, False
        execucao = cls(
            item_ordem_servico=item,
            status=StatusExecucaoValvula.RASCUNHO,
            resultado=ResultadoExecucaoValvula.PENDENTE,
            data_inicio=timezone.localdate(),
        )
        execucao.registrar_execucao(user, limpar_revisao=False)
        execucao.save()
        item.sincronizar_com_execucao_valvula(execucao)
        return execucao, True

    @property
    def servico_solicitado(self):
        return self.item_ordem_servico.servico_solicitado

    @property
    def eh_manutencao(self):
        return self.servico_solicitado == ServicoSolicitado.MANUTENCAO

    @property
    def eh_ensaio(self):
        return self.servico_solicitado == ServicoSolicitado.ENSAIO

    @property
    def pressao_ajuste_cadastrada_formatada(self):
        if self.valvula_pressao_ajuste in (None, ""):
            return ""
        valor_decimal = self.valvula_pressao_ajuste
        if not isinstance(valor_decimal, Decimal):
            valor_decimal = Decimal(str(valor_decimal))
        unidade = self.valvula_unidade_pressao or UnidadePressao.PSI
        valor = format(valor_decimal, "f").rstrip("0").rstrip(".")
        return f"{valor} {unidade}"

    @property
    def pode_editar(self):
        if self.status != StatusExecucaoValvula.RASCUNHO:
            return False
        return self.item_ordem_servico.status != StatusItemOrdem.AGUARDANDO_REVISAO

    @property
    def pode_enviar_revisao(self):
        return (
            self.status == StatusExecucaoValvula.RASCUNHO
            and not self.esta_revisada
            and self.item_ordem_servico.status
            != StatusItemOrdem.AGUARDANDO_REVISAO
        )

    @property
    def pode_revisar(self):
        return (
            self.status == StatusExecucaoValvula.RASCUNHO
            and not self.esta_revisada
            and self.item_ordem_servico.status
            == StatusItemOrdem.AGUARDANDO_REVISAO
        )

    @property
    def pode_concluir(self):
        return (
            self.status == StatusExecucaoValvula.RASCUNHO
            and self.esta_revisada
        )

    @property
    def pode_cancelar(self):
        return self.status == StatusExecucaoValvula.RASCUNHO

    @property
    def esta_revisada(self):
        return bool(self.revisado_em and (self.revisor_nome or "").strip())

    def texto_servico_minimo(self):
        return (self.descricao_servico or self.observacoes or "").strip()

    def validar_envio_revisao(self):
        erros = []
        if not (self.executor_nome or "").strip():
            erros.append("Registre o responsável pela execução.")
        if not self.data_inicio:
            erros.append("Informe a data de início da execução.")
        if not self.texto_servico_minimo():
            erros.append(
                "Descreva o serviço realizado ou registre uma observação antes de enviar para revisão."
            )
        if self.resultado not in (
            ResultadoExecucaoValvula.APROVADO,
            ResultadoExecucaoValvula.REPROVADO,
        ):
            erros.append(
                "Defina o resultado (aprovado ou reprovado) antes de enviar para revisão."
            )
        return erros

    def validar_conclusao(self):
        erros = self.validar_envio_revisao()
        if not self.esta_revisada:
            erros.append("Registre a revisão técnica antes de concluir a execução.")
        return erros

    def registrar_execucao(self, user, limpar_revisao=True):
        self.executor = user
        self.executor_nome = identificacao_usuario(user)
        self.executado_em = timezone.now()
        if limpar_revisao:
            self.limpar_revisao()
        return self

    def registrar_revisao(self, user):
        if self.status != StatusExecucaoValvula.RASCUNHO:
            return False
        if not (self.executor_nome or "").strip():
            self.registrar_execucao(user, limpar_revisao=False)
        self.revisor = user
        self.revisor_nome = identificacao_usuario(user)
        self.revisado_em = timezone.now()
        return True

    def limpar_revisao(self):
        self.revisor = None
        self.revisor_nome = ""
        self.revisado_em = None
        return self


class StatusOrcamento(models.TextChoices):
    RASCUNHO = "rascunho", "Rascunho"
    ENVIADO = "enviado", "Enviado"
    APROVADO = "aprovado", "Aprovado"
    RECUSADO = "recusado", "Recusado"
    EXPIRADO = "expirado", "Expirado"
    CANCELADO = "cancelado", "Cancelado"


class Orcamento(models.Model):
    numero = models.CharField(max_length=50, unique=True, blank=True)
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name="orcamentos",
    )
    data_emissao = models.DateField()
    data_validade = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=StatusOrcamento.choices,
        default=StatusOrcamento.RASCUNHO,
    )
    observacoes = models.TextField(blank=True)
    condicoes_comerciais = models.TextField(blank=True)
    cliente_nome_snapshot = models.CharField(max_length=150, blank=True)
    cliente_documento_snapshot = models.CharField(max_length=18, blank=True)
    cliente_endereco_snapshot = models.CharField(max_length=255, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Orçamento"
        verbose_name_plural = "Orçamentos"
        ordering = ["-data_emissao", "-criado_em"]
        indexes = [
            models.Index(fields=["numero"]),
            models.Index(fields=["status"]),
            models.Index(fields=["data_emissao"]),
        ]
        permissions = [
            ("enviar_orcamento", "Pode enviar orçamento"),
            ("aprovar_orcamento", "Pode aprovar orçamento"),
            ("recusar_orcamento", "Pode recusar orçamento"),
            ("cancelar_orcamento", "Pode cancelar orçamento"),
            ("gerar_ordem_servico", "Pode gerar ordem de serviço a partir do orçamento"),
        ]

    def __str__(self):
        return self.numero or "ORC"

    def save(self, *args, **kwargs):
        if not (self.numero or "").strip():
            self.numero = self.proximo_numero()
        else:
            self.numero = self.numero.strip()
        super().save(*args, **kwargs)

    @classmethod
    def proximo_numero(cls):
        existentes = cls.objects.values_list("numero", flat=True)
        maior = 0
        prefixo = "ORC-"
        for numero in existentes:
            if not numero:
                continue
            if numero.upper().startswith(prefixo) and numero[4:].isdigit():
                maior = max(maior, int(numero[4:]))
        return f"{prefixo}{maior + 1:06d}"

    @classmethod
    def criar(cls, **dados):
        for _ in range(8):
            try:
                with transaction.atomic():
                    list(cls.objects.select_for_update().order_by("pk")[:1])
                    orcamento = cls(**dados)
                    if not (orcamento.numero or "").strip():
                        orcamento.numero = cls.proximo_numero()
                    orcamento.aplicar_snapshot_cliente()
                    orcamento.save()
                    return orcamento
            except IntegrityError:
                continue
        raise IntegrityError("Não foi possível gerar um número único de orçamento.")

    def aplicar_snapshot_cliente(self):
        if not self.cliente_id:
            return
        cliente = self.cliente
        self.cliente_nome_snapshot = cliente.nome
        self.cliente_documento_snapshot = cliente.cnpj
        self.cliente_endereco_snapshot = f"{cliente.endereco} — CEP {cliente.cep}"
        return self

    @property
    def cliente_nome_exibicao(self):
        return self.cliente_nome_snapshot or (self.cliente.nome if self.cliente_id else "")

    @property
    def cliente_documento_exibicao(self):
        return self.cliente_documento_snapshot or (
            self.cliente.cnpj if self.cliente_id else ""
        )

    @property
    def cliente_endereco_exibicao(self):
        return self.cliente_endereco_snapshot or (
            self.cliente.endereco if self.cliente_id else ""
        )

    @property
    def pode_editar(self):
        return self.status == StatusOrcamento.RASCUNHO

    @property
    def pode_enviar(self):
        return self.status == StatusOrcamento.RASCUNHO

    @property
    def pode_voltar_rascunho(self):
        return self.status == StatusOrcamento.ENVIADO

    @property
    def prazo_expirado(self):
        if not self.data_validade:
            return False
        if self.status in (
            StatusOrcamento.APROVADO,
            StatusOrcamento.RECUSADO,
            StatusOrcamento.CANCELADO,
            StatusOrcamento.EXPIRADO,
        ):
            return self.status == StatusOrcamento.EXPIRADO
        return timezone.localdate() > self.data_validade

    @property
    def situacao_prazo(self):
        if self.status == StatusOrcamento.EXPIRADO:
            return "expirado", "Expirado"
        if not self.data_validade:
            return "sem_prazo", "Sem prazo"
        if self.status in (
            StatusOrcamento.APROVADO,
            StatusOrcamento.RECUSADO,
            StatusOrcamento.CANCELADO,
        ):
            return "encerrado", self.get_status_display()
        if timezone.localdate() > self.data_validade:
            return "expirado", "Expirado"
        return "valido", "No prazo"

    @property
    def pode_aprovar(self):
        return self.status == StatusOrcamento.ENVIADO and not self.prazo_expirado

    @property
    def pode_recusar(self):
        return self.status == StatusOrcamento.ENVIADO

    @property
    def pode_cancelar(self):
        return self.status in (
            StatusOrcamento.RASCUNHO,
            StatusOrcamento.ENVIADO,
        )

    @property
    def pode_expirar(self):
        return self.status == StatusOrcamento.ENVIADO and self.prazo_expirado

    @property
    def ordem_gerada(self):
        return self.ordens_servico.order_by("pk").first()

    @property
    def pode_gerar_os(self):
        return self.status == StatusOrcamento.APROVADO and self.ordem_gerada is None

    def transicoes_permitidas(self):
        return {
            StatusOrcamento.RASCUNHO: {
                StatusOrcamento.ENVIADO,
                StatusOrcamento.CANCELADO,
            },
            StatusOrcamento.ENVIADO: {
                StatusOrcamento.APROVADO,
                StatusOrcamento.RECUSADO,
                StatusOrcamento.CANCELADO,
                StatusOrcamento.EXPIRADO,
                StatusOrcamento.RASCUNHO,
            },
            StatusOrcamento.APROVADO: set(),
            StatusOrcamento.RECUSADO: set(),
            StatusOrcamento.EXPIRADO: set(),
            StatusOrcamento.CANCELADO: set(),
        }.get(self.status, set())

    def erros_envio(self):
        erros = []
        if not self.cliente_id:
            erros.append("O orçamento precisa de um cliente.")
        itens = list(self.itens.all())
        if not itens:
            erros.append("Inclua pelo menos um item no orçamento.")
        for item in itens:
            try:
                item.full_clean()
            except ValidationError as exc:
                erros.append(str(exc))
        return erros

    def totais(self):
        itens = list(self.itens.all())
        subtotal = sum((item.subtotal for item in itens), Decimal("0.00"))
        desconto = sum((item.desconto or Decimal("0.00") for item in itens), Decimal("0.00"))
        total = sum((item.total for item in itens), Decimal("0.00"))
        return {
            "subtotal": subtotal.quantize(Decimal("0.01")),
            "desconto": desconto.quantize(Decimal("0.01")),
            "total": total.quantize(Decimal("0.01")),
        }

    def alterar_status(self, novo_status):
        if novo_status not in self.transicoes_permitidas():
            return False, "Transição de status não permitida para este orçamento."
        if novo_status == StatusOrcamento.ENVIADO:
            erros = self.erros_envio()
            if erros:
                return False, erros[0]
            self.aplicar_snapshot_cliente()
            for item in self.itens.select_related("instrumento", "valvula"):
                item.aplicar_snapshot_equipamento()
                item.save()
        if novo_status == StatusOrcamento.APROVADO:
            erros = self.erros_envio()
            if erros:
                return False, erros[0]
            if self.prazo_expirado:
                return False, "Orçamento com validade vencida não pode ser aprovado."
        campos = ["status", "atualizado_em"]
        if novo_status == StatusOrcamento.ENVIADO:
            campos.extend(
                [
                    "cliente_nome_snapshot",
                    "cliente_documento_snapshot",
                    "cliente_endereco_snapshot",
                ]
            )
        self.status = novo_status
        self.save(update_fields=campos)
        return True, ""

    def gerar_ordem_servico(self):
        if not self.pode_gerar_os:
            existente = self.ordem_gerada
            if existente:
                return existente, "OS já gerada."
            return None, "Somente orçamento aprovado, sem OS, pode gerar ordem de serviço."
        itens = list(
            self.itens.select_related("instrumento", "valvula").order_by("ordem", "pk")
        )
        unicos = []
        vistos = set()
        for item in itens:
            if item.instrumento_id:
                chave = ("i", item.instrumento_id)
            elif item.valvula_id:
                chave = ("v", item.valvula_id)
            else:
                continue
            if chave in vistos:
                continue
            vistos.add(chave)
            unicos.append(item)
        if not unicos:
            return None, "Inclua ao menos um item com equipamento para gerar a OS."
        with transaction.atomic():
            list(OrdemServico.objects.select_for_update().order_by("pk")[:1])
            list(type(self).objects.select_for_update().filter(pk=self.pk))
            self.refresh_from_db()
            if self.ordem_gerada:
                return self.ordem_gerada, "OS já gerada."
            cliente = self.cliente
            contato = cliente.dados_contato()
            ordem = OrdemServico.criar(
                cliente=cliente,
                data_entrada=timezone.localdate(),
                solicitante=contato["contato_principal"],
                telefone_solicitante=contato["telefone"],
                email_solicitante=contato["email"],
                contato_solicitante=contato["telefone"] or contato["email"],
                observacoes=f"Gerada a partir do orçamento {self.numero}.",
                orcamento=self,
            )
            for item in unicos:
                dados_item = {
                    "ordem_servico": ordem,
                    "servico_solicitado": item.servico,
                    "observacoes": item.descricao,
                }
                if item.instrumento_id:
                    dados_item["tipo_equipamento"] = TipoEquipamento.INSTRUMENTO
                    dados_item["instrumento"] = item.instrumento
                else:
                    dados_item["tipo_equipamento"] = TipoEquipamento.VALVULA
                    dados_item["valvula"] = item.valvula
                os_item = ItemOrdemServico(**dados_item)
                os_item.full_clean()
                os_item.save()
            ordem.alterar_status(StatusOrdemServico.RECEBIDA)
            return ordem, ""


class ItemOrcamento(models.Model):
    orcamento = models.ForeignKey(
        Orcamento,
        on_delete=models.PROTECT,
        related_name="itens",
    )
    servico = models.CharField(
        max_length=20,
        choices=ServicoSolicitado.choices,
        default=ServicoSolicitado.CALIBRACAO,
    )
    tipo_equipamento = models.CharField(
        max_length=20,
        choices=TipoEquipamento.choices,
        blank=True,
        default="",
    )
    instrumento = models.ForeignKey(
        Instrumento,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="itens_orcamento",
    )
    valvula = models.ForeignKey(
        "Valvula",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="itens_orcamento",
    )
    descricao = models.TextField()
    quantidade = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    valor_unitario = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    desconto = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    total = models.DecimalField(max_digits=12, decimal_places=2)
    ordem = models.PositiveIntegerField(default=1)
    instrumento_codigo_snapshot = models.CharField(max_length=50, blank=True)
    instrumento_tag_snapshot = models.CharField(max_length=100, blank=True)
    instrumento_serie_snapshot = models.CharField(max_length=100, blank=True)
    valvula_codigo_snapshot = models.CharField(max_length=50, blank=True)
    valvula_tag_snapshot = models.CharField(max_length=100, blank=True)
    valvula_serie_snapshot = models.CharField(max_length=100, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Item do orçamento"
        verbose_name_plural = "Itens do orçamento"
        ordering = ["ordem", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantidade__gte=1),
                name="item_orcamento_quantidade_positiva",
            ),
            models.CheckConstraint(
                condition=models.Q(valor_unitario__gte=0),
                name="item_orcamento_valor_nao_negativo",
            ),
            models.CheckConstraint(
                condition=models.Q(desconto__gte=0),
                name="item_orcamento_desconto_nao_negativo",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(instrumento__isnull=True) | models.Q(valvula__isnull=True)
                ),
                name="item_orcamento_equipamento_exclusivo",
            ),
        ]

    def __str__(self):
        return f"{self.orcamento.numero} — item {self.ordem}"

    @property
    def subtotal(self):
        return (Decimal(self.quantidade) * self.valor_unitario).quantize(
            Decimal("0.01")
        )

    def calcular_total(self):
        total = self.subtotal - (self.desconto or Decimal("0.00"))
        if total < 0:
            raise ValidationError(
                {"desconto": "O desconto não pode ser maior que o subtotal do item."}
            )
        return total.quantize(Decimal("0.01"))

    def aplicar_snapshot_instrumento(self):
        self.aplicar_snapshot_equipamento()

    def aplicar_snapshot_equipamento(self):
        if self.instrumento_id and not self.valvula_id:
            self.tipo_equipamento = TipoEquipamento.INSTRUMENTO
        elif self.valvula_id and not self.instrumento_id:
            self.tipo_equipamento = TipoEquipamento.VALVULA
        if self.instrumento_id:
            instrumento = self.instrumento
            self.instrumento_codigo_snapshot = instrumento.codigo
            self.instrumento_tag_snapshot = instrumento.tag
            self.instrumento_serie_snapshot = instrumento.numero_serie
        else:
            self.instrumento_codigo_snapshot = ""
            self.instrumento_tag_snapshot = ""
            self.instrumento_serie_snapshot = ""
        if self.valvula_id:
            valvula = self.valvula
            self.valvula_codigo_snapshot = valvula.codigo
            self.valvula_tag_snapshot = valvula.tag
            self.valvula_serie_snapshot = valvula.numero_serie
        else:
            self.valvula_codigo_snapshot = ""
            self.valvula_tag_snapshot = ""
            self.valvula_serie_snapshot = ""

    @property
    def codigo_equipamento_exibicao(self):
        if self.instrumento_codigo_snapshot or self.instrumento_id:
            if self.instrumento_codigo_snapshot:
                return self.instrumento_codigo_snapshot
            return self.instrumento.codigo if self.instrumento_id else ""
        if self.valvula_codigo_snapshot or self.valvula_id:
            if self.valvula_codigo_snapshot:
                return self.valvula_codigo_snapshot
            return self.valvula.codigo if self.valvula_id else ""
        return ""

    def clean_fields(self, exclude=None):
        exclude = set(exclude or [])
        exclude.add("total")
        super().clean_fields(exclude=exclude)

    def clean(self):
        super().clean()
        if self.instrumento_id and self.valvula_id:
            raise ValidationError(
                "O item do orçamento deve apontar para um manômetro ou para uma válvula, nunca para os dois."
            )
        if self.orcamento_id and self.instrumento_id:
            if self.instrumento.cliente_id != self.orcamento.cliente_id:
                raise ValidationError(
                    {
                        "instrumento": "O instrumento deve pertencer ao mesmo cliente do orçamento."
                    }
                )
        if self.orcamento_id and self.valvula_id:
            if self.valvula.cliente_id != self.orcamento.cliente_id:
                raise ValidationError(
                    {
                        "valvula": "A válvula deve pertencer ao mesmo cliente do orçamento."
                    }
                )
        try:
            self.total = self.calcular_total()
        except ValidationError:
            raise

    def save(self, *args, **kwargs):
        if self.orcamento_id and self.orcamento.status == StatusOrcamento.RASCUNHO:
            self.aplicar_snapshot_equipamento()
        self.total = self.calcular_total()
        super().save(*args, **kwargs)


class FormaPagamento(models.TextChoices):
    BOLETO = "boleto", "Boleto"
    PIX = "pix", "PIX"
    DINHEIRO = "dinheiro", "Dinheiro"
    TRANSFERENCIA = "transferencia", "Transferência"
    CARTAO = "cartao", "Cartão"
    OUTRO = "outro", "Outro"


class StatusCobranca(models.TextChoices):
    PENDENTE = "pendente", "Pendente"
    PARCIAL = "parcial", "Parcial"
    PAGO = "pago", "Pago"
    VENCIDO = "vencido", "Vencido"
    CANCELADO = "cancelado", "Cancelado"


class Cobranca(models.Model):
    numero = models.CharField(max_length=50, unique=True, blank=True)
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name="cobrancas",
    )
    orcamento = models.ForeignKey(
        Orcamento,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cobrancas",
    )
    ordem_servico = models.ForeignKey(
        OrdemServico,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cobrancas",
    )
    descricao = models.CharField(max_length=255)
    valor_original = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    desconto = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    acrescimo = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    valor_final = models.DecimalField(max_digits=12, decimal_places=2)
    data_emissao = models.DateField()
    data_vencimento = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=StatusCobranca.choices,
        default=StatusCobranca.PENDENTE,
    )
    forma_pagamento = models.CharField(
        max_length=20,
        choices=FormaPagamento.choices,
        blank=True,
    )
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Cobrança"
        verbose_name_plural = "Cobranças"
        ordering = ["-data_emissao", "-criado_em"]
        indexes = [
            models.Index(fields=["numero"]),
            models.Index(fields=["status"]),
            models.Index(fields=["data_vencimento"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(valor_original__gte=0),
                name="cobranca_valor_original_nao_negativo",
            ),
            models.CheckConstraint(
                condition=models.Q(desconto__gte=0),
                name="cobranca_desconto_nao_negativo",
            ),
            models.CheckConstraint(
                condition=models.Q(acrescimo__gte=0),
                name="cobranca_acrescimo_nao_negativo",
            ),
            models.UniqueConstraint(
                fields=["ordem_servico"],
                condition=models.Q(ordem_servico__isnull=False),
                name="uniq_cobranca_ordem_servico",
            ),
        ]
        permissions = [
            ("cancelar_cobranca", "Pode cancelar cobrança"),
            ("registrar_pagamento", "Pode registrar pagamento"),
        ]

    def __str__(self):
        return self.numero or "COB"

    def delete(self, using=None, keep_parents=False):
        raise ValidationError("Cobranças não podem ser excluídas. Cancele a cobrança.")

    def save(self, *args, **kwargs):
        if self.status == StatusCobranca.VENCIDO:
            self.status = StatusCobranca.PENDENTE
        if not (self.numero or "").strip():
            self.numero = self.proximo_numero()
        else:
            self.numero = self.numero.strip()
        self.valor_final = self.calcular_valor_final()
        super().save(*args, **kwargs)

    @classmethod
    def proximo_numero(cls):
        existentes = cls.objects.values_list("numero", flat=True)
        maior = 0
        prefixo = "COB-"
        for numero in existentes:
            if not numero:
                continue
            if numero.upper().startswith(prefixo) and numero[4:].isdigit():
                maior = max(maior, int(numero[4:]))
        return f"{prefixo}{maior + 1:06d}"

    @classmethod
    def criar(cls, **dados):
        for _ in range(8):
            try:
                with transaction.atomic():
                    list(cls.objects.select_for_update().order_by("pk")[:1])
                    cobranca = cls(**dados)
                    if not (cobranca.numero or "").strip():
                        cobranca.numero = cls.proximo_numero()
                    cobranca.full_clean()
                    cobranca.save()
                    return cobranca
            except IntegrityError:
                if dados.get("ordem_servico") and cls.objects.filter(
                    ordem_servico=dados["ordem_servico"]
                ).exists():
                    raise
                continue
        raise IntegrityError("Não foi possível gerar um número único de cobrança.")

    def calcular_valor_final(self):
        original = self.valor_original or Decimal("0.00")
        desconto = self.desconto or Decimal("0.00")
        acrescimo = self.acrescimo or Decimal("0.00")
        return (original - desconto + acrescimo).quantize(Decimal("0.01"))

    def total_pago(self):
        anotado = getattr(self, "total_pago_agg", None)
        if anotado is not None:
            return Decimal(anotado).quantize(Decimal("0.01"))
        agregado = self.pagamentos.aggregate(
            total=Coalesce(
                Sum("valor"),
                Value(Decimal("0.00")),
                output_field=models.DecimalField(max_digits=12, decimal_places=2),
            )
        )
        return (agregado["total"] or Decimal("0.00")).quantize(Decimal("0.01"))

    def saldo_devedor(self):
        saldo = self.valor_final - self.total_pago()
        if saldo < 0:
            return Decimal("0.00")
        return saldo.quantize(Decimal("0.01"))

    @property
    def esta_cancelada(self):
        return self.status == StatusCobranca.CANCELADO

    @property
    def esta_paga(self):
        if self.esta_cancelada:
            return False
        return self.saldo_devedor() <= Decimal("0.00")

    @property
    def esta_vencida(self):
        if self.esta_cancelada or self.esta_paga:
            return False
        return self.data_vencimento < timezone.localdate()

    @property
    def situacao(self):
        if self.esta_cancelada:
            return StatusCobranca.CANCELADO, "Cancelado"
        if self.esta_paga:
            return StatusCobranca.PAGO, "Pago"
        if self.esta_vencida:
            return StatusCobranca.VENCIDO, "Vencido"
        if self.total_pago() > Decimal("0.00"):
            return StatusCobranca.PARCIAL, "Parcial"
        return StatusCobranca.PENDENTE, "Pendente"

    @property
    def situacao_codigo(self):
        return self.situacao[0]

    @property
    def situacao_rotulo(self):
        return self.situacao[1]

    @property
    def pode_editar(self):
        if self.status != StatusCobranca.PENDENTE:
            return False
        quantidade = getattr(self, "qtd_pagamentos", None)
        if quantidade is not None:
            return quantidade == 0
        return not self.pagamentos.exists()

    @property
    def pode_pagar(self):
        return not self.esta_cancelada and not self.esta_paga

    @property
    def pode_cancelar(self):
        return not self.esta_cancelada and not self.esta_paga

    def clean_fields(self, exclude=None):
        exclude = set(exclude or [])
        exclude.add("valor_final")
        super().clean_fields(exclude=exclude)

    def clean(self):
        super().clean()
        self.valor_final = self.calcular_valor_final()
        if self.valor_final < 0:
            raise ValidationError(
                {"desconto": "O desconto não pode deixar o valor final negativo."}
            )
        if self.orcamento_id and self.orcamento.cliente_id != self.cliente_id:
            raise ValidationError(
                {"orcamento": "O orçamento deve pertencer ao mesmo cliente da cobrança."}
            )
        if self.ordem_servico_id and self.ordem_servico.cliente_id != self.cliente_id:
            raise ValidationError(
                {
                    "ordem_servico": "A ordem de serviço deve pertencer ao mesmo cliente da cobrança."
                }
            )
        if self.orcamento_id and self.ordem_servico_id:
            origem = self.ordem_servico.orcamento_id
            if origem and origem != self.orcamento_id:
                raise ValidationError(
                    {
                        "ordem_servico": "A ordem de serviço não pertence a este orçamento."
                    }
                )

    def sincronizar_status_pagamento(self):
        if self.esta_cancelada:
            return self.status
        pago = self.total_pago()
        if pago >= self.valor_final:
            self.status = StatusCobranca.PAGO
        elif pago > 0:
            self.status = StatusCobranca.PARCIAL
        else:
            self.status = StatusCobranca.PENDENTE
        self.save(update_fields=["status", "atualizado_em"])
        return self.status

    def cancelar(self):
        if not self.pode_cancelar:
            return False, "Cobrança paga ou já cancelada não pode ser cancelada."
        self.status = StatusCobranca.CANCELADO
        self.save(update_fields=["status", "atualizado_em"])
        return True, ""

    def registrar_pagamento(self, *, data_pagamento, valor, forma_pagamento, observacoes=""):
        with transaction.atomic():
            cobranca = type(self).objects.select_for_update().get(pk=self.pk)
            pagamento = Pagamento(
                cobranca=cobranca,
                data_pagamento=data_pagamento,
                valor=valor,
                forma_pagamento=forma_pagamento,
                observacoes=observacoes or "",
            )
            pagamento.full_clean()
            pagamento.save()
            cobranca.sincronizar_status_pagamento()
            return pagamento


class Pagamento(models.Model):
    cobranca = models.ForeignKey(
        Cobranca,
        on_delete=models.PROTECT,
        related_name="pagamentos",
    )
    data_pagamento = models.DateField()
    valor = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    forma_pagamento = models.CharField(
        max_length=20,
        choices=FormaPagamento.choices,
    )
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Pagamento"
        verbose_name_plural = "Pagamentos"
        ordering = ["data_pagamento", "pk"]

    def __str__(self):
        return f"{self.cobranca.numero} — {self.valor}"

    def delete(self, using=None, keep_parents=False):
        raise ValidationError("Pagamentos não podem ser excluídos.")

    def clean(self):
        super().clean()
        if self.valor is None or self.valor <= 0:
            raise ValidationError({"valor": "O valor do pagamento deve ser maior que zero."})
        cobranca = self.cobranca
        if cobranca.esta_cancelada:
            raise ValidationError("Não é possível registrar pagamento em cobrança cancelada.")
        if cobranca.esta_paga and not self.pk:
            raise ValidationError("Esta cobrança já está paga.")
        pago = cobranca.total_pago()
        if self.pk:
            atual = type(self).objects.filter(pk=self.pk).values_list("valor", flat=True).first()
            if atual:
                pago -= atual
        saldo = cobranca.valor_final - pago
        if self.valor > saldo:
            raise ValidationError(
                {"valor": "O pagamento não pode ultrapassar o saldo da cobrança."}
            )


class Calibracao(models.Model):
    instrumento = models.ForeignKey(
        Instrumento,
        on_delete=models.PROTECT,
        related_name="calibracoes",
    )
    item_ordem_servico = models.ForeignKey(
        "ItemOrdemServico",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="calibracoes",
    )
    numero = models.CharField(
        max_length=50,
        blank=True,
        help_text="Identificação persistente da calibração, única por instrumento.",
    )
    data_calibracao = models.DateField()
    procedimento = models.CharField(max_length=150, blank=True)
    padrao = models.ForeignKey(
        PadraoMedicao,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="calibracoes",
    )
    padrao_utilizado = models.TextField(
        blank=True,
        help_text="Snapshot documental do padrão utilizado nesta calibração.",
    )
    criterio_aceitacao = models.CharField(
        max_length=255,
        blank=True,
        help_text="Origem do critério informado para esta calibração. Não implica norma automática.",
    )
    tolerancia = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        blank=True,
        null=True,
        help_text="Tolerância absoluta na unidade do instrumento. Zero exige erro nulo.",
    )
    observacoes = models.TextField(blank=True)
    executor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="calibracoes_executadas",
    )
    executor_nome = models.CharField(max_length=150, blank=True)
    executado_em = models.DateTimeField(null=True, blank=True)
    revisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="calibracoes_revisadas",
    )
    revisor_nome = models.CharField(max_length=150, blank=True)
    revisado_em = models.DateTimeField(null=True, blank=True)
    intervalo_validade_meses = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Prazo documental em meses, se informado. Não implica norma automática.",
    )
    data_validade = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=StatusCalibracao.choices,
        default=StatusCalibracao.RASCUNHO,
    )
    resultado = models.CharField(
        max_length=20,
        choices=ResultadoCalibracao.choices,
        default=ResultadoCalibracao.PENDENTE,
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Calibração"
        verbose_name_plural = "Calibrações"
        ordering = ["-data_calibracao", "-criado_em"]
        constraints = [
            models.UniqueConstraint(
                fields=["instrumento", "numero"],
                name="uniq_calibracao_instrumento_numero",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(tolerancia__isnull=True)
                    | models.Q(tolerancia__gte=0)
                ),
                name="calibracao_tolerancia_nao_negativa",
            ),
        ]
        indexes = [
            models.Index(fields=["numero"]),
            models.Index(fields=["data_calibracao"]),
            models.Index(fields=["status"]),
            models.Index(fields=["resultado"]),
        ]
        permissions = [
            ("concluir_calibracao", "Pode concluir calibração"),
            ("revisar_calibracao", "Pode revisar calibração"),
            ("reabrir_calibracao", "Pode reabrir calibração"),
        ]

    def __str__(self):
        return f"{self.numero} — {self.instrumento.codigo}"

    def save(self, *args, **kwargs):
        if not (self.numero or "").strip() and self.instrumento_id:
            self.numero = self.proximo_numero(self.instrumento)
        elif self.numero:
            self.numero = self.numero.strip()
        if self.status == StatusCalibracao.RASCUNHO:
            self.aplicar_snapshot_padrao()
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        item = self.item_ordem_servico
        if not item:
            return
        if item.instrumento_id != self.instrumento_id:
            raise ValidationError(
                {
                    "item_ordem_servico": "A calibração deve usar o mesmo instrumento do item da ordem de serviço."
                }
            )
        if item.ordem_servico.cliente_id != self.instrumento.cliente_id:
            raise ValidationError(
                {
                    "item_ordem_servico": "A calibração e a ordem de serviço devem pertencer ao mesmo cliente."
                }
            )

    @classmethod
    def abrir_para_item(cls, item, user):
        if not item.exige_calibracao or not item.instrumento_id:
            raise ValidationError(
                "A calibração só pode ser iniciada para um item de manômetro com serviço de calibração."
            )
        if item.ordem_servico.status in (
            StatusOrdemServico.ENTREGUE,
            StatusOrdemServico.CANCELADA,
        ):
            raise ValidationError("Esta ordem de serviço não pode mais ser alterada.")
        existente = item.calibracao_atual
        if existente and existente.status != StatusCalibracao.CANCELADA:
            item.sincronizar_com_calibracao(existente)
            return existente, False
        calibracao = cls(
            instrumento=item.instrumento,
            item_ordem_servico=item,
            data_calibracao=timezone.localdate(),
            status=StatusCalibracao.RASCUNHO,
            resultado=ResultadoCalibracao.PENDENTE,
        )
        calibracao.registrar_execucao(user, limpar_revisao=False)
        calibracao.save()
        item.sincronizar_com_calibracao(calibracao)
        return calibracao, True

    def aplicar_snapshot_padrao(self):
        if not self.padrao_id:
            return
        padrao = self.padrao
        self.padrao_utilizado = padrao.rotulo_documento()
        return self.padrao_utilizado

    @classmethod
    def proximo_numero(cls, instrumento):
        existentes = cls.objects.filter(instrumento=instrumento).values_list(
            "numero",
            flat=True,
        )
        maior = 0
        for numero in existentes:
            if not numero:
                continue
            prefixo = "CAL-"
            if numero.upper().startswith(prefixo) and numero[4:].isdigit():
                maior = max(maior, int(numero[4:]))
        return f"CAL-{maior + 1:04d}"

    @property
    def certificado_atual(self):
        try:
            return self.certificado
        except CertificadoCalibracao.DoesNotExist:
            return None

    @property
    def pode_editar(self):
        return self.status == StatusCalibracao.RASCUNHO

    @property
    def pode_cancelar(self):
        if self.status == StatusCalibracao.CANCELADA:
            return False
        certificado = self.certificado_atual
        if certificado and certificado.esta_valido:
            return False
        return True

    @property
    def pode_concluir(self):
        return self.status == StatusCalibracao.RASCUNHO

    @property
    def esta_revisada(self):
        return bool(self.revisado_em and (self.revisor_nome or "").strip())

    @property
    def pode_revisar(self):
        return self.status == StatusCalibracao.RASCUNHO and not self.esta_revisada

    @property
    def pode_reabrir(self):
        if self.status != StatusCalibracao.CONCLUIDA:
            return False
        certificado = self.certificado_atual
        if certificado and certificado.esta_valido:
            return False
        return True

    @property
    def pode_emitir_certificado(self):
        if self.status != StatusCalibracao.CONCLUIDA:
            return False
        if self.resultado not in (
            ResultadoCalibracao.APROVADO,
            ResultadoCalibracao.REPROVADO,
        ):
            return False
        return self.certificado_atual is None

    @property
    def tolerancia_formatada(self):
        if self.tolerancia is None:
            return ""
        valor = Instrumento._formatar_decimal(self.tolerancia)
        unidade = ""
        if self.instrumento_id:
            unidade = self.instrumento.unidade or ""
        return f"±{valor} {unidade}".strip()

    @property
    def data_proxima_calibracao(self):
        return self.data_validade

    @property
    def validade_expirada(self):
        if not self.data_validade:
            return False
        return timezone.localdate() > self.data_validade

    @staticmethod
    def adicionar_meses(data, meses):
        return data + relativedelta(months=int(meses))

    def atualizar_validade(self):
        if self.intervalo_validade_meses:
            self.data_validade = self.adicionar_meses(
                self.data_calibracao,
                self.intervalo_validade_meses,
            )
        else:
            self.data_validade = None
        return self.data_validade

    def validar_ensaio(self):
        erros = []
        if not (self.criterio_aceitacao or "").strip():
            erros.append("Informe o critério de aceitação para concluir a calibração.")
        if self.tolerancia is None:
            erros.append("Informe a tolerância para concluir a calibração.")
        elif self.tolerancia < 0:
            erros.append("A tolerância não pode ser negativa.")
        if not self.pontos.exists():
            erros.append("Informe pelo menos um ponto de ensaio para concluir a calibração.")
        return erros

    def validar_conclusao(self):
        erros = self.validar_ensaio()
        if not (self.executor_nome or "").strip():
            erros.append("Registre o responsável pela execução antes de concluir.")
        if not self.esta_revisada:
            erros.append("Registre a revisão/aprovação antes de concluir a calibração.")
        if self.intervalo_validade_meses is not None and self.intervalo_validade_meses < 1:
            erros.append("O intervalo de validade, se informado, deve ser de pelo menos 1 mês.")
        return erros

    def registrar_execucao(self, user, limpar_revisao=True):
        self.executor = user
        self.executor_nome = identificacao_usuario(user)
        self.executado_em = timezone.now()
        if limpar_revisao:
            self.revisor = None
            self.revisor_nome = ""
            self.revisado_em = None
        return self

    def registrar_revisao(self, user):
        if self.status != StatusCalibracao.RASCUNHO:
            return False
        if not (self.executor_nome or "").strip():
            self.registrar_execucao(user, limpar_revisao=False)
        self.revisor = user
        self.revisor_nome = identificacao_usuario(user)
        self.revisado_em = timezone.now()
        return True

    def limpar_revisao(self):
        self.revisor = None
        self.revisor_nome = ""
        self.revisado_em = None
        return self

    def calcular_resultado(self):
        if self.status != StatusCalibracao.CONCLUIDA:
            return ResultadoCalibracao.PENDENTE
        if self.tolerancia is None:
            return ResultadoCalibracao.PENDENTE
        pontos = list(self.pontos.all())
        if not pontos:
            return ResultadoCalibracao.PENDENTE
        if all(ponto.dentro_da_tolerancia for ponto in pontos):
            return ResultadoCalibracao.APROVADO
        return ResultadoCalibracao.REPROVADO

    def aplicar_resultado_oficial(self):
        self.resultado = self.calcular_resultado()
        return self.resultado

    def resumo_aceitacao(self):
        pontos = list(self.pontos.all())
        aprovados = 0
        reprovados = 0
        pendentes = 0
        maior_abs = None
        for ponto in pontos:
            situacao = ponto.dentro_da_tolerancia
            if situacao is True:
                aprovados += 1
            elif situacao is False:
                reprovados += 1
            else:
                pendentes += 1
            if ponto.erro is not None:
                atual = abs(ponto.erro)
                if maior_abs is None or atual > maior_abs:
                    maior_abs = atual
        unidade = ""
        if self.instrumento_id:
            unidade = self.instrumento.unidade or ""
        maior_formatado = ""
        if maior_abs is not None:
            maior_formatado = f"{Instrumento._formatar_decimal(maior_abs)} {unidade}".strip()
        return {
            "avaliados": len(pontos),
            "aprovados": aprovados,
            "reprovados": reprovados,
            "pendentes": pendentes,
            "maior_erro_absoluto": maior_abs,
            "maior_erro_absoluto_formatado": maior_formatado,
        }


class PontoCalibracao(models.Model):
    calibracao = models.ForeignKey(
        Calibracao,
        on_delete=models.CASCADE,
        related_name="pontos",
    )
    ordem = models.PositiveIntegerField()
    valor_referencia = models.DecimalField(max_digits=12, decimal_places=3)
    indicacao_instrumento = models.DecimalField(max_digits=12, decimal_places=3)
    erro = models.DecimalField(max_digits=12, decimal_places=3)
    observacoes = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "Ponto de calibração"
        verbose_name_plural = "Pontos de calibração"
        ordering = ["ordem"]
        constraints = [
            models.UniqueConstraint(
                fields=["calibracao", "ordem"],
                name="uniq_ponto_calibracao_ordem",
            ),
            models.CheckConstraint(
                condition=models.Q(ordem__gte=1),
                name="ponto_calibracao_ordem_positiva",
            ),
        ]

    def __str__(self):
        return f"Ponto {self.ordem} — {self.calibracao.numero}"

    def save(self, *args, **kwargs):
        self.erro = self.calcular_erro(
            self.indicacao_instrumento,
            self.valor_referencia,
        )
        super().save(*args, **kwargs)

    @staticmethod
    def calcular_erro(indicacao, referencia):
        if not isinstance(indicacao, Decimal):
            indicacao = Decimal(str(indicacao))
        if not isinstance(referencia, Decimal):
            referencia = Decimal(str(referencia))
        return indicacao - referencia

    def _valor_com_unidade(self, valor):
        texto = Instrumento._formatar_decimal(valor)
        unidade = ""
        if self.calibracao_id:
            unidade = self.calibracao.instrumento.unidade or ""
        return f"{texto} {unidade}".strip()

    @property
    def valor_referencia_formatado(self):
        return self._valor_com_unidade(self.valor_referencia)

    @property
    def indicacao_formatada(self):
        return self._valor_com_unidade(self.indicacao_instrumento)

    @property
    def erro_formatado(self):
        if self.erro is None:
            return ""
        valor = Instrumento._formatar_decimal(self.erro)
        if self.erro > 0:
            valor = f"+{valor}"
        unidade = ""
        if self.calibracao_id:
            unidade = self.calibracao.instrumento.unidade or ""
        return f"{valor} {unidade}".strip()

    @property
    def erro_absoluto(self):
        if self.erro is None:
            return None
        return abs(self.erro)

    @property
    def dentro_da_tolerancia(self):
        if self.erro is None or not self.calibracao_id:
            return None
        tolerancia = self.calibracao.tolerancia
        if tolerancia is None:
            return None
        return abs(self.erro) <= tolerancia

    @property
    def resultado_avaliacao(self):
        situacao = self.dentro_da_tolerancia
        if situacao is None:
            return ResultadoCalibracao.PENDENTE
        if situacao:
            return ResultadoCalibracao.APROVADO
        return ResultadoCalibracao.REPROVADO

    @property
    def resultado_avaliacao_display(self):
        return ResultadoCalibracao(self.resultado_avaliacao).label


class StatusCertificado(models.TextChoices):
    EMITIDO = "emitido", "Emitido"
    CANCELADO = "cancelado", "Cancelado"


class CertificadoCalibracao(models.Model):
    calibracao = models.OneToOneField(
        Calibracao,
        on_delete=models.PROTECT,
        related_name="certificado",
    )
    numero = models.CharField(max_length=50, unique=True)
    emitido_em = models.DateTimeField()
    status = models.CharField(
        max_length=20,
        choices=StatusCertificado.choices,
        default=StatusCertificado.EMITIDO,
    )
    token_validacao = models.CharField(
        max_length=64,
        unique=True,
        default=gerar_token_avulso,
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Certificado de calibração"
        verbose_name_plural = "Certificados de calibração"
        ordering = ["-emitido_em", "-criado_em"]
        indexes = [
            models.Index(fields=["numero"]),
            models.Index(fields=["status"]),
        ]
        permissions = [
            ("emitir_certificado", "Pode emitir certificado de calibração"),
            ("cancelar_certificado", "Pode cancelar certificado de calibração"),
        ]

    def __str__(self):
        return self.numero

    @property
    def esta_valido(self):
        return self.status == StatusCertificado.EMITIDO

    @property
    def pode_cancelar(self):
        return self.status == StatusCertificado.EMITIDO

    @classmethod
    def proximo_numero(cls):
        existentes = cls.objects.values_list("numero", flat=True)
        maior = 0
        prefixo = "CERT-"
        for numero in existentes:
            if not numero:
                continue
            if numero.upper().startswith(prefixo) and numero[5:].isdigit():
                maior = max(maior, int(numero[5:]))
        return f"{prefixo}{maior + 1:06d}"

    @classmethod
    def gerar_token_validacao(cls):
        for _ in range(16):
            token = secrets.token_urlsafe(32)
            if not cls.objects.filter(token_validacao=token).exists():
                return token
        raise RuntimeError("Não foi possível gerar um token de validação único.")

    @classmethod
    def emitir_para(cls, calibracao):
        existente = cls.objects.filter(calibracao=calibracao).first()
        if existente:
            return existente, False
        if not calibracao.pode_emitir_certificado:
            return None, False
        calibracao.atualizar_validade()
        calibracao.save(update_fields=["data_validade", "atualizado_em"])
        for _ in range(8):
            try:
                with transaction.atomic():
                    list(cls.objects.select_for_update().order_by("pk")[:1])
                    certificado = cls(
                        calibracao=calibracao,
                        numero=cls.proximo_numero(),
                        emitido_em=timezone.now(),
                        status=StatusCertificado.EMITIDO,
                        token_validacao=cls.gerar_token_validacao(),
                    )
                    certificado.save()
                    return certificado, True
            except IntegrityError:
                existente = cls.objects.filter(calibracao=calibracao).first()
                if existente:
                    return existente, False
        return None, False


class RelatorioTecnico(models.Model):

    # =========================================================
    # CLIENTE
    # =========================================================

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name="relatorios_tecnicos"
    )

    # =========================================================
    # IDENTIFICAÇÃO DO RELATÓRIO
    # =========================================================

    numero_relatorio = models.CharField(
        max_length=50,
        blank=True,
        null=True
    )

    folha = models.CharField(
        max_length=20,
        default="01"
    )

    item = models.CharField(
        max_length=50,
        blank=True,
        null=True
    )

    # =========================================================
    # DADOS DO RELATÓRIO
    # =========================================================

    setor = models.CharField(
        max_length=150,
        blank=True,
        null=True
    )

    data = models.DateField(
        blank=True,
        null=True
    )

    # =========================================================
    # MOTIVO DO RELATÓRIO
    # =========================================================

    motivo_solicitacao_cliente = models.BooleanField(
        default=False
    )

    motivo_manutencao_corretiva = models.BooleanField(
        default=False
    )

    motivo_garantia = models.BooleanField(
        default=False
    )

    motivo_manutencao_preventiva = models.BooleanField(
        default=False
    )

    motivo_venda = models.BooleanField(
        default=False
    )

    # =========================================================
    # OBSERVAÇÕES
    # =========================================================

    observacoes = models.TextField(
        blank=True,
        null=True
    )

    # =========================================================
    # MOTIVO PRINCIPAL DA REFORMA
    # =========================================================

    motivo_instalacao_irregular = models.BooleanField(
        default=False
    )

    motivo_escolha_inadequada = models.BooleanField(
        default=False
    )

    motivo_condicoes_criticas = models.BooleanField(
        default=False
    )

    motivo_entrada_impurezas = models.BooleanField(
        default=False
    )

    motivo_manuseio_irregular = models.BooleanField(
        default=False
    )

    motivo_transporte_irregular = models.BooleanField(
        default=False
    )

    motivo_desgaste_normal = models.BooleanField(
        default=False
    )

    motivo_lacre_quebrado = models.BooleanField(
        default=False
    )

    # =========================================================
    # PRAZO
    # =========================================================

    prazo_entrega = models.DateField(
        blank=True,
        null=True
    )

    # =========================================================
    # APROVAÇÃO
    # =========================================================

    data_aprovacao = models.DateField(
        blank=True,
        null=True
    )

    # =========================================================
    # CONTROLE
    # =========================================================

    criado_em = models.DateTimeField(
        auto_now_add=True
    )

    atualizado_em = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        if self.numero_relatorio:
            return f"Relatório {self.numero_relatorio} - {self.cliente.nome}"

        return f"Relatório #{self.pk} - {self.cliente.nome}"

    class Meta:
        verbose_name = "Relatório Técnico"
        verbose_name_plural = "Relatórios Técnicos"
        ordering = ["-criado_em"]


class ValvulaRelatorio(models.Model):

    relatorio = models.ForeignKey(
        RelatorioTecnico,
        on_delete=models.CASCADE,
        related_name="valvulas"
    )
    valvula = models.ForeignKey(
        "Valvula",
        on_delete=models.PROTECT,
        related_name="itens_relatorio",
        blank=True,
        null=True,
    )

    # =========================================================
    # IDENTIFICAÇÃO
    # =========================================================

    item = models.PositiveIntegerField(
        default=1
    )

    numero_serie = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    tag = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    diametro = models.CharField(
        max_length=50,
        blank=True,
        null=True
    )

    modelo = models.CharField(
        max_length=150,
        blank=True,
        null=True
    )

    fabricante = models.CharField(
        max_length=150,
        blank=True,
        null=True
    )

    pressao_psi = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    servico = models.CharField(
        max_length=150,
        blank=True,
        null=True
    )

    observacao = models.TextField(
        blank=True,
        null=True
    )

    criado_em = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        verbose_name = "Válvula do Relatório"
        verbose_name_plural = "Válvulas dos Relatórios"
        ordering = ["item"]

    def __str__(self):
        return (
            f"Item {self.item} - "
            f"{self.tag or self.numero_serie or 'Válvula'}"
        )
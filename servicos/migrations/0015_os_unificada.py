# Generated manually for FASE 1 — OS unificada

import django.db.models.deletion
from django.db import migrations, models


def preencher_tipo_equipamento(apps, schema_editor):
    ItemOrdemServico = apps.get_model("servicos", "ItemOrdemServico")
    ItemOrdemServico.objects.filter(instrumento_id__isnull=False).update(
        tipo_equipamento="instrumento"
    )


def noop(apps, schema_editor):
    return None


class Migration(migrations.Migration):

    dependencies = [
        ("servicos", "0014_permissoes_auditoria"),
    ]

    operations = [
        migrations.AddField(
            model_name="ordemservico",
            name="contato_solicitante",
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddField(
            model_name="ordemservico",
            name="responsavel_recebimento",
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddField(
            model_name="ordemservico",
            name="data_conclusao",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="ordemservico",
            name="status",
            field=models.CharField(
                choices=[
                    ("aberta", "Aberta"),
                    ("recebida", "Recebida"),
                    ("em_execucao", "Em execução"),
                    ("aguardando_revisao", "Aguardando revisão"),
                    ("concluida", "Concluída"),
                    ("entregue", "Entregue"),
                    ("cancelada", "Cancelada"),
                ],
                default="aberta",
                max_length=30,
            ),
        ),
        migrations.AlterModelOptions(
            name="ordemservico",
            options={
                "ordering": ["-criado_em"],
                "permissions": [
                    ("receber_ordem", "Pode receber ordem de serviço"),
                    ("iniciar_ordem", "Pode iniciar ordem de serviço"),
                    ("revisar_ordem", "Pode enviar ordem de serviço para revisão"),
                    ("concluir_ordem", "Pode concluir ordem de serviço"),
                    ("entregar_ordem", "Pode entregar ordem de serviço"),
                    ("cancelar_ordem", "Pode cancelar ordem de serviço"),
                ],
                "verbose_name": "Ordem de serviço",
                "verbose_name_plural": "Ordens de serviço",
            },
        ),
        migrations.AddField(
            model_name="itemordemservico",
            name="tipo_equipamento",
            field=models.CharField(
                choices=[
                    ("instrumento", "Manômetro"),
                    ("valvula", "Válvula"),
                ],
                default="instrumento",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="itemordemservico",
            name="valvula",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="itens_ordem_servico",
                to="servicos.valvula",
            ),
        ),
        migrations.AddField(
            model_name="itemordemservico",
            name="observacoes_recebimento",
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name="itemordemservico",
            name="instrumento",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="itens_ordem_servico",
                to="servicos.instrumento",
            ),
        ),
        migrations.AlterField(
            model_name="itemordemservico",
            name="servico_solicitado",
            field=models.CharField(
                choices=[
                    ("calibracao", "Calibração"),
                    ("ensaio", "Ensaio"),
                    ("ajuste", "Ajuste"),
                    ("inspecao", "Inspeção"),
                    ("manutencao", "Manutenção"),
                    ("outro", "Outro"),
                ],
                default="calibracao",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="itemorcamento",
            name="servico",
            field=models.CharField(
                choices=[
                    ("calibracao", "Calibração"),
                    ("ensaio", "Ensaio"),
                    ("ajuste", "Ajuste"),
                    ("inspecao", "Inspeção"),
                    ("manutencao", "Manutenção"),
                    ("outro", "Outro"),
                ],
                default="calibracao",
                max_length=20,
            ),
        ),
        migrations.RunPython(preencher_tipo_equipamento, noop),
        migrations.RemoveConstraint(
            model_name="itemordemservico",
            name="uniq_item_os_instrumento",
        ),
        migrations.AddConstraint(
            model_name="itemordemservico",
            constraint=models.UniqueConstraint(
                condition=models.Q(("instrumento__isnull", False)),
                fields=("ordem_servico", "instrumento"),
                name="uniq_item_os_instrumento",
            ),
        ),
        migrations.AddConstraint(
            model_name="itemordemservico",
            constraint=models.UniqueConstraint(
                condition=models.Q(("valvula__isnull", False)),
                fields=("ordem_servico", "valvula"),
                name="uniq_item_os_valvula",
            ),
        ),
        migrations.AddConstraint(
            model_name="itemordemservico",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        ("tipo_equipamento", "instrumento"),
                        ("instrumento__isnull", False),
                        ("valvula__isnull", True),
                    )
                    | models.Q(
                        ("tipo_equipamento", "valvula"),
                        ("valvula__isnull", False),
                        ("instrumento__isnull", True),
                    )
                ),
                name="item_os_um_equipamento",
            ),
        ),
    ]

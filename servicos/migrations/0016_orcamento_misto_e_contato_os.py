import django.db.models.deletion
from django.db import migrations, models


def preencher_tipo_item_orcamento(apps, schema_editor):
    ItemOrcamento = apps.get_model("servicos", "ItemOrcamento")
    ItemOrcamento.objects.filter(instrumento_id__isnull=False).update(
        tipo_equipamento="instrumento"
    )


def noop(apps, schema_editor):
    return None


class Migration(migrations.Migration):

    dependencies = [
        ("servicos", "0015_os_unificada"),
        ("clientes", "0002_contato"),
    ]

    operations = [
        migrations.AddField(
            model_name="ordemservico",
            name="telefone_solicitante",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="ordemservico",
            name="email_solicitante",
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name="itemorcamento",
            name="tipo_equipamento",
            field=models.CharField(
                blank=True,
                choices=[
                    ("instrumento", "Manômetro"),
                    ("valvula", "Válvula"),
                ],
                default="",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="itemorcamento",
            name="valvula",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="itens_orcamento",
                to="servicos.valvula",
            ),
        ),
        migrations.AddField(
            model_name="itemorcamento",
            name="valvula_codigo_snapshot",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="itemorcamento",
            name="valvula_tag_snapshot",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="itemorcamento",
            name="valvula_serie_snapshot",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.RunPython(preencher_tipo_item_orcamento, noop),
        migrations.AddConstraint(
            model_name="itemorcamento",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("instrumento__isnull", True))
                    | models.Q(("valvula__isnull", True))
                ),
                name="item_orcamento_equipamento_exclusivo",
            ),
        ),
    ]

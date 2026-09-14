import secrets

from django.db import migrations, models

import servicos.models


def preencher_tokens(apps, schema_editor):
    Certificado = apps.get_model("servicos", "CertificadoCalibracao")
    existentes = set()
    for certificado in Certificado.objects.all():
        token = secrets.token_urlsafe(32)
        while token in existentes:
            token = secrets.token_urlsafe(32)
        existentes.add(token)
        certificado.token_validacao = token
        certificado.save(update_fields=["token_validacao"])


class Migration(migrations.Migration):

    dependencies = [
        ("servicos", "0007_calibracao_responsabilidade"),
    ]

    operations = [
        migrations.AddField(
            model_name="certificadocalibracao",
            name="token_validacao",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.RunPython(preencher_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="certificadocalibracao",
            name="token_validacao",
            field=models.CharField(
                default=servicos.models.gerar_token_avulso,
                max_length=64,
                unique=True,
            ),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clientes", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="cliente",
            name="contato_principal",
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddField(
            model_name="cliente",
            name="telefone",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="cliente",
            name="email",
            field=models.EmailField(blank=True, max_length=254),
        ),
    ]

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0003_crear_perfiles_existentes'),
    ]

    operations = [
        migrations.AlterField(
            model_name='registroinr',
            name='fechaLectura',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]

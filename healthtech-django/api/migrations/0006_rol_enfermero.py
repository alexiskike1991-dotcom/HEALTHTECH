from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0005_enlace_cuidador'),
    ]

    operations = [
        migrations.AlterField(
            model_name='perfilusuario',
            name='rol',
            field=models.CharField(choices=[('paciente', 'Paciente'), ('medico', 'Enfermero/a')], default='paciente', max_length=20),
        ),
    ]

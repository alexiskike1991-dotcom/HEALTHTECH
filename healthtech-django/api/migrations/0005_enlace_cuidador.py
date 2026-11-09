import api.models
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0004_fecha_lectura_editable'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='EnlaceCuidador',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token', models.CharField(db_index=True, default=api.models._nuevo_token, max_length=64, unique=True)),
                ('ficha', models.JSONField(blank=True, default=dict)),
                ('creado', models.DateTimeField(auto_now_add=True)),
                ('usuario', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='enlace_cuidador', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]

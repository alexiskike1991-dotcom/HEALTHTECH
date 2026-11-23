import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0006_rol_enfermero'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Receta',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('imagen', models.BinaryField()),
                ('datos', models.JSONField(blank=True, default=dict)),
                ('creada', models.DateTimeField(default=django.utils.timezone.now)),
                ('usuario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='recetas', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-creada', '-id']},
        ),
    ]

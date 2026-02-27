# Generated migration for AccessLog model

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('medical_inventory', '0009_alter_medication_medication_type'),
    ]

    operations = [
        migrations.CreateModel(
            name='AccessLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event_type', models.CharField(
                    max_length=10,
                    choices=[('UNLOCK', 'Unlock'), ('RESTOCK', 'Restock')],
                    default='UNLOCK'
                )),
                ('timestamp', models.DateTimeField(default=django.utils.timezone.now)),
                ('door_open_seconds', models.IntegerField(null=True, blank=True, help_text='Seconds the door was open (unlocks only)')),
                ('notes', models.TextField(blank=True)),
                ('astronaut', models.ForeignKey(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='medical_inventory.astronaut',
                    related_name='access_logs'
                )),
            ],
            options={'ordering': ['-timestamp']},
        ),
        migrations.CreateModel(
            name='AccessLogItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.IntegerField()),
                ('access_log', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    to='medical_inventory.accesslog',
                    related_name='items'
                )),
                ('medication', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    to='medical_inventory.medication'
                )),
            ],
        ),
    ]

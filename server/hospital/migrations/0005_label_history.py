# Create HospitalLabelHistory audit table (DRT-5204 §B9 D11).

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hospital', '0004_backfill_category_to_dimensions'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='HospitalLabelHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('changed_at', models.DateTimeField(auto_now_add=True)),
                ('field_name', models.CharField(max_length=64)),
                ('old_value', models.JSONField(blank=True, null=True)),
                ('new_value', models.JSONField()),
                ('source', models.CharField(max_length=16)),
                ('confidence', models.DecimalField(blank=True, decimal_places=3, max_digits=4, null=True)),
                ('sourcing_job_id', models.BigIntegerField(blank=True, null=True)),
                ('changed_by', models.ForeignKey(
                    blank=True,
                    db_constraint=False,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('hospital', models.ForeignKey(
                    db_constraint=False,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='label_history',
                    to='hospital.hospital',
                )),
            ],
            options={
                'db_table': 'hospital_label_history',
            },
        ),
        migrations.AddIndex(
            model_name='hospitallabelhistory',
            index=models.Index(fields=['hospital', '-changed_at'], name='idx_hlh_hospital_changed'),
        ),
        migrations.AddIndex(
            model_name='hospitallabelhistory',
            index=models.Index(fields=['sourcing_job_id'], name='idx_hlh_sourcing_job'),
        ),
    ]

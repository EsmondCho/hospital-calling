# Create SourcingJob (DRT-5204 §2).

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SourcingJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('state_code', models.CharField(max_length=2)),
                ('city', models.CharField(blank=True, max_length=128, null=True)),
                ('latitude', models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ('longitude', models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ('radius_km', models.PositiveIntegerField(default=50)),
                ('is_dry_run', models.BooleanField(default=False)),
                ('force_refresh', models.BooleanField(default=False)),
                ('refresh_after_days', models.PositiveIntegerField(default=90)),
                ('status', models.CharField(default='PENDING', max_length=16)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('error_message', models.TextField(blank=True, null=True)),
                ('page_cursor', models.TextField(blank=True, null=True)),
                ('last_place_id', models.CharField(blank=True, max_length=128, null=True)),
                ('fetched_count', models.PositiveIntegerField(default=0)),
                ('inserted_count', models.PositiveIntegerField(default=0)),
                ('updated_count', models.PositiveIntegerField(default=0)),
                ('skipped_count', models.PositiveIntegerField(default=0)),
                ('excluded_count', models.PositiveIntegerField(default=0)),
                ('needs_review_count', models.PositiveIntegerField(default=0)),
                ('error_count', models.PositiveIntegerField(default=0)),
                ('estimated_places_count', models.PositiveIntegerField(blank=True, null=True)),
                ('estimated_cost_usd', models.DecimalField(blank=True, decimal_places=4, max_digits=8, null=True)),
                ('actual_cost_usd', models.DecimalField(decimal_places=4, default=0, max_digits=8)),
                ('llm_input_tokens', models.PositiveBigIntegerField(default=0)),
                ('llm_output_tokens', models.PositiveBigIntegerField(default=0)),
                ('triggered_by', models.ForeignKey(
                    blank=True,
                    db_constraint=False,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'sourcing_job',
            },
        ),
        migrations.AddIndex(
            model_name='sourcingjob',
            index=models.Index(fields=['status', '-created_at'], name='idx_sj_status_created'),
        ),
        migrations.AddIndex(
            model_name='sourcingjob',
            index=models.Index(fields=['state_code', 'city', 'status'], name='idx_sj_loc_status'),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ('hospital', '0001_initial'),
        ('prompt', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='CallSchedule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('scheduled_at', models.DateTimeField()),
                ('status', models.CharField(default='PENDING', max_length=20)),
                ('label', models.CharField(blank=True, max_length=200, null=True)),
                ('metadata', models.JSONField(default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('hospital', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=models.deletion.SET_NULL, to='hospital.hospital')),
                ('prompt', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=models.deletion.SET_NULL, to='prompt.prompt')),
            ],
            options={
                'db_table': 'call_schedule',
                'ordering': ['-scheduled_at'],
            },
        ),
        migrations.CreateModel(
            name='CallAttempt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('blandai_call_id', models.CharField(blank=True, max_length=128, null=True, unique=True)),
                ('recording_url', models.URLField(blank=True, max_length=500, null=True)),
                ('status', models.CharField(default='QUEUED', max_length=20)),
                ('answered_by', models.CharField(blank=True, max_length=20, null=True)),
                ('call_ended_by', models.CharField(blank=True, max_length=20, null=True)),
                ('failure_reason', models.TextField(blank=True, null=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('ended_at', models.DateTimeField(blank=True, null=True)),
                ('duration_seconds', models.PositiveIntegerField(blank=True, null=True)),
                ('summary', models.TextField(blank=True, null=True)),
                ('transcript', models.JSONField(default=list)),
                ('metadata', models.JSONField(default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('hospital', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=models.deletion.SET_NULL, to='hospital.hospital')),
                ('prompt', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=models.deletion.SET_NULL, to='prompt.prompt')),
                ('schedule', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=models.deletion.SET_NULL, to='calling.callschedule')),
            ],
            options={
                'db_table': 'call_attempt',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='callschedule',
            index=models.Index(fields=['status', 'scheduled_at'], name='idx_csched_status_at'),
        ),
        migrations.AddIndex(
            model_name='callattempt',
            index=models.Index(fields=['status', '-created_at'], name='idx_cattempt_status_at'),
        ),
        migrations.AddIndex(
            model_name='callattempt',
            index=models.Index(fields=['hospital', '-created_at'], name='idx_cattempt_hosp_at'),
        ),
        migrations.AddIndex(
            model_name='callattempt',
            index=models.Index(fields=['schedule'], name='idx_cattempt_schedule'),
        ),
    ]

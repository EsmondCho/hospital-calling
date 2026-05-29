from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Hospital',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('source', models.CharField(max_length=32)),
                ('source_external_id', models.CharField(blank=True, max_length=128, null=True)),
                ('phone_e164', models.CharField(blank=True, max_length=24, null=True)),
                ('website', models.URLField(blank=True, max_length=500, null=True)),
                ('formatted_address', models.CharField(blank=True, max_length=500, null=True)),
                ('city', models.CharField(blank=True, max_length=100, null=True)),
                ('state', models.CharField(blank=True, max_length=2, null=True)),
                ('postal_code', models.CharField(blank=True, max_length=16, null=True)),
                ('timezone', models.CharField(blank=True, max_length=64, null=True)),
                ('latitude', models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ('longitude', models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ('category', models.CharField(default='UNKNOWN', max_length=32)),
                ('is_callable', models.BooleanField(default=True)),
                ('excluded_reason', models.CharField(blank=True, max_length=200, null=True)),
                ('metadata', models.JSONField(default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'db_table': 'hospital'},
        ),
        migrations.AddIndex(
            model_name='hospital',
            index=models.Index(fields=['category', 'is_callable'], name='idx_hospital_cat_call'),
        ),
        migrations.AddIndex(
            model_name='hospital',
            index=models.Index(fields=['state'], name='idx_hospital_state'),
        ),
        migrations.AddConstraint(
            model_name='hospital',
            constraint=models.UniqueConstraint(
                condition=models.Q(('source_external_id__isnull', False)),
                fields=('source', 'source_external_id'),
                name='uq_hospital_source_external',
            ),
        ),
    ]

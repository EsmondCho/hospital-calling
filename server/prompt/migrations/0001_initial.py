from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Prompt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.SlugField(max_length=80)),
                ('objective', models.CharField(max_length=32)),
                ('version', models.PositiveIntegerField()),
                ('body', models.TextField()),
                ('voice', models.CharField(blank=True, max_length=64, null=True)),
                ('model', models.CharField(blank=True, max_length=64, null=True)),
                ('language', models.CharField(default='en', max_length=16)),
                ('is_active', models.BooleanField(default=False)),
                ('notes', models.TextField(blank=True, null=True)),
                ('metadata', models.JSONField(default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'db_table': 'prompt'},
        ),
        migrations.AddIndex(
            model_name='prompt',
            index=models.Index(fields=['objective', 'is_active'], name='idx_prompt_obj_active'),
        ),
        migrations.AddConstraint(
            model_name='prompt',
            constraint=models.UniqueConstraint(
                fields=('name', 'version'), name='uq_prompt_name_version'
            ),
        ),
        migrations.AddConstraint(
            model_name='prompt',
            constraint=models.UniqueConstraint(
                condition=models.Q(('is_active', True)),
                fields=('name',),
                name='uq_prompt_active_per_name',
            ),
        ),
    ]

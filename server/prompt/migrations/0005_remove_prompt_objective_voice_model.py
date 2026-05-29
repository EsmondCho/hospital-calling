from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('prompt', '0004_remove_prompt_uq_prompt_active_per_name_and_more'),
    ]
    operations = [
        migrations.RemoveField(model_name='prompt', name='objective'),
        migrations.RemoveField(model_name='prompt', name='voice'),
        migrations.RemoveField(model_name='prompt', name='model'),
    ]

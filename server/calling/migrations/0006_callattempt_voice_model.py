from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('calling', '0005_callschedule_memo_voice_model'),
    ]
    operations = [
        migrations.AddField(
            model_name='callattempt',
            name='voice',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
        migrations.AddField(
            model_name='callattempt',
            name='model',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
    ]

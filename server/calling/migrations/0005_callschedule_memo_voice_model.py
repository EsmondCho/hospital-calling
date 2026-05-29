from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('calling', '0004_callattempt_is_deleted_callschedule_is_deleted'),
    ]
    operations = [
        migrations.RenameField(
            model_name='callschedule', old_name='label', new_name='memo'
        ),
        migrations.AddField(
            model_name='callschedule',
            name='voice',
            field=models.CharField(default='random', max_length=20),
        ),
        migrations.AddField(
            model_name='callschedule',
            name='model',
            field=models.CharField(default='base', max_length=20),
        ),
    ]

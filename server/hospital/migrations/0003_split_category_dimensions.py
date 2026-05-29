# Split Hospital.category (single enum) into ownership + service_tags +
# appointment_mode + label provenance fields (DRT-5204 §1).
#
# Forward-only column additions; the actual data backfill from legacy `category`
# happens in 0004. Legacy column `category` and `is_callable` are intentionally
# kept (read-compatible) for `dispatch_schedule` — they will be dropped in a
# follow-up coordinated with DRT-5206.

import django.contrib.postgres.fields
import django.db.models.deletion
from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hospital', '0002_hospital_is_deleted'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='hospital',
            name='ownership',
            field=models.CharField(default='UNCLASSIFIED', max_length=32),
        ),
        migrations.AddField(
            model_name='hospital',
            name='service_tags',
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.CharField(max_length=32),
                blank=True,
                default=list,
                size=None,
            ),
        ),
        migrations.AddField(
            model_name='hospital',
            name='appointment_mode',
            field=models.CharField(default='UNKNOWN', max_length=32),
        ),
        migrations.AddField(
            model_name='hospital',
            name='label_source',
            field=models.CharField(blank=True, max_length=16, null=True),
        ),
        migrations.AddField(
            model_name='hospital',
            name='label_locked',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='hospital',
            name='confidence',
            field=models.DecimalField(blank=True, decimal_places=3, max_digits=4, null=True),
        ),
        migrations.AddField(
            model_name='hospital',
            name='reviewed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='hospital',
            name='reviewed_by',
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='+',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name='hospital',
            index=models.Index(fields=['ownership', 'is_callable'], name='idx_hospital_own_call'),
        ),
        migrations.AddIndex(
            model_name='hospital',
            index=GinIndex(fields=['service_tags'], name='idx_hospital_svctags_gin'),
        ),
        migrations.AddIndex(
            model_name='hospital',
            index=models.Index(fields=['label_source', 'confidence'], name='idx_hospital_lbl_conf'),
        ),
    ]

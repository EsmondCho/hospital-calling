# Drop the legacy single-axis classification and the label-history audit
# table; add `specialty_areas` (DRT-5204 follow-up cleanup).
#
# Removed:
#   - Hospital.category      — superseded by ownership + service_tags
#   - Hospital.is_callable   — call targeting now derives from ownership
#                              (`dispatch_schedule` checks ownership == INDEPENDENT)
#   - Hospital.confidence    — per-row LLM confidence no longer persisted
#   - Hospital.label_source  — `label_locked` alone tracks human review
#   - HospitalLabelHistory   — audit table dropped (single-operator tool)
#
# Added:
#   - Hospital.specialty_areas — free-text specialty list (cardiology, ...)

import django.contrib.postgres.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hospital', '0005_label_history'),
    ]

    operations = [
        # Indexes first — they reference columns we're about to drop.
        migrations.RemoveIndex(model_name='hospital', name='idx_hospital_cat_call'),
        migrations.RemoveIndex(model_name='hospital', name='idx_hospital_own_call'),
        migrations.RemoveIndex(model_name='hospital', name='idx_hospital_lbl_conf'),

        migrations.RemoveField(model_name='hospital', name='category'),
        migrations.RemoveField(model_name='hospital', name='is_callable'),
        migrations.RemoveField(model_name='hospital', name='confidence'),
        migrations.RemoveField(model_name='hospital', name='label_source'),

        migrations.AddField(
            model_name='hospital',
            name='specialty_areas',
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.CharField(max_length=64),
                blank=True,
                default=list,
                size=None,
            ),
        ),
        migrations.AddIndex(
            model_name='hospital',
            index=models.Index(fields=['ownership'], name='idx_hospital_ownership'),
        ),

        migrations.DeleteModel(name='HospitalLabelHistory'),
    ]

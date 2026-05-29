"""Backfill `CallScheduleHospital` from the legacy single `CallSchedule.hospital`.

Each existing schedule had exactly one hospital (1:1). Copy it into the new
ordered through table as `order=0`, deriving the step status from any
CallAttempt the schedule already produced so an in-flight row keeps its place
in the (now sequential) state machine. The next migration drops the legacy
`hospital` column.
"""

from django.db import migrations

# Literals, not the vars enums — a migration must not couple to the enum class.
_TERMINAL_CALL_STATUSES = ('COMPLETED', 'FAILED')


def backfill_targets(apps, schema_editor):
    CallSchedule = apps.get_model('calling', 'CallSchedule')
    CallAttempt = apps.get_model('calling', 'CallAttempt')
    CallScheduleHospital = apps.get_model('calling', 'CallScheduleHospital')

    rows = []
    for sched in CallSchedule.objects.exclude(hospital_id__isnull=True).iterator():
        attempt = (
            CallAttempt.objects.filter(
                schedule_id=sched.id, hospital_id=sched.hospital_id
            )
            .order_by('-created_at')
            .first()
        )
        if attempt is not None:
            status = 'DONE' if attempt.status in _TERMINAL_CALL_STATUSES else 'DIALING'
        elif sched.status == 'SKIPPED':
            status = 'SKIPPED'
        else:
            status = 'PENDING'
        rows.append(
            CallScheduleHospital(
                schedule_id=sched.id,
                hospital_id=sched.hospital_id,
                order=0,
                status=status,
                call_attempt_id=attempt.id if attempt else None,
            )
        )
    CallScheduleHospital.objects.bulk_create(rows, batch_size=500)


def drop_targets(apps, schema_editor):
    CallScheduleHospital = apps.get_model('calling', 'CallScheduleHospital')
    CallScheduleHospital.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('calling', '0008_callcomment_callschedulehospital_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_targets, drop_targets),
    ]

"""Backfill new 3-axis labels from legacy Hospital.category (DRT-5204 §A3, §E1).

Runs after the dummy data seed (`calling/0002_seed_dummy_data`) so the 6
seeded rows get mapped to the new taxonomy. Idempotent: rows that already
have a non-default ownership / service_tags / appointment_mode or that we
already tagged with `label_source='IMPORT'` are skipped, so operators who
manually corrected rows and reruns of this migration are both safe.

Information loss is intentional. The legacy `category` enum mashed two
orthogonal dimensions (ownership and service) together, so for old values
like ER_OR_URGENT / WALK_IN_ONLY we can recover the service axis but not
the ownership axis — those rows land at `ownership=UNCLASSIFIED`. Prod is
empty apart from the 6 dummy rows at the time of this migration, so the
loss is bounded; the sourcing pipeline (DRT-5204 §2) re-classifies on its
first run.
"""

from django.db import migrations


# legacy category → (ownership, service_tags, appointment_mode)
MAPPING = {
    'LOCAL':           ('INDEPENDENT',     ['GENERAL_PRACTICE'],                    'UNKNOWN'),
    'CHAIN':           ('CHAIN',           ['GENERAL_PRACTICE'],                    'UNKNOWN'),
    'RETAIL_EMBEDDED': ('RETAIL_EMBEDDED', ['RETAIL_WELLNESS', 'GENERAL_PRACTICE'], 'WALK_IN_ALLOWED'),
    'ER_OR_URGENT':    ('UNCLASSIFIED',    ['EMERGENCY'],                           'UNKNOWN'),
    'WALK_IN_ONLY':    ('UNCLASSIFIED',    ['GENERAL_PRACTICE'],                    'WALK_IN_ONLY'),
    'NON_CLINIC':      ('UNCLASSIFIED',    [],                                      'UNKNOWN'),
    'UNKNOWN':         ('UNCLASSIFIED',    [],                                      'UNKNOWN'),
}


def forwards(apps, schema_editor):  # noqa: ARG001
    Hospital = apps.get_model('hospital', 'Hospital')
    fallback = MAPPING['UNKNOWN']
    to_update: list = []

    for h in Hospital.objects.all():
        # Skip rows that have already been classified (by us or an operator).
        # Checking label_source also catches NON_CLINIC / UNKNOWN rows whose
        # mapped values happen to match the defaults — once we tag them
        # IMPORT, rerunning won't reprocess them.
        already_processed = (
            h.ownership != 'UNCLASSIFIED'
            or h.service_tags
            or h.appointment_mode != 'UNKNOWN'
            or h.label_source is not None
        )
        if already_processed:
            continue
        ownership, tags, mode = MAPPING.get(h.category, fallback)
        h.ownership = ownership
        h.service_tags = list(tags)
        h.appointment_mode = mode
        h.label_source = 'IMPORT'
        to_update.append(h)

    if to_update:
        Hospital.objects.bulk_update(
            to_update,
            ['ownership', 'service_tags', 'appointment_mode', 'label_source'],
        )


def backwards(apps, schema_editor):  # noqa: ARG001
    """Only reset rows we set ourselves. Operator-corrected rows are not touched
    (label_source flips off IMPORT the moment any other writer runs)."""
    Hospital = apps.get_model('hospital', 'Hospital')
    Hospital.objects.filter(label_source='IMPORT').update(
        ownership='UNCLASSIFIED',
        service_tags=[],
        appointment_mode='UNKNOWN',
        label_source=None,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('hospital', '0003_split_category_dimensions'),
        # Run after the dummy data seed so the 6 seeded rows are present.
        ('calling', '0002_seed_dummy_data'),
    ]

    operations = [
        migrations.RunPython(forwards, reverse_code=backwards),
    ]

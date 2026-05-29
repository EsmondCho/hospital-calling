# Move the chain keyword table from a Python constant into the DB so it can
# be browsed in the backoffice and tuned via the Django admin console
# (DRT-5204 follow-up). Seeds the 20 chains the constant table carried.

import django.contrib.postgres.fields
from django.db import migrations, models


# (priority, chain_brand_normalized, display_name, ownership, service_tags,
#  regex_pattern, notes)
_SEED = [
    (10, 'vca', 'VCA Animal Hospitals', 'MARS_VH',
     ['GENERAL_PRACTICE', 'SPECIALTY', 'EMERGENCY'], r'\bVCA\b',
     'Individual locations vary in ER coverage — LLM verifies per-site.'),
    (20, 'banfield', 'Banfield Pet Hospital', 'MARS_VH',
     ['RETAIL_WELLNESS', 'GENERAL_PRACTICE'], r"\bBanfield\b(?!'s)",
     'Operates inside PetSmart locations. Lookahead skips possessive "Banfield\'s".'),
    (30, 'bluepearl', 'BluePearl', 'MARS_VH',
     ['SPECIALTY', 'EMERGENCY'], r'BluePearl|Blue Pearl', ''),
    (40, 'pet_partners', 'Pet Partners (Mars)', 'MARS_VH',
     ['GENERAL_PRACTICE'], r'Pet Partners',
     'Smaller Mars rollup — name collides with non-vet brands.'),
    (50, 'nva', 'National Veterinary Associates', 'CHAIN',
     ['GENERAL_PRACTICE', 'EMERGENCY'], r'\bNVA\b|National Veterinary Associates',
     'Retains local brand names at most sites — LLM second pass essential.'),
    (60, 'compassion_first', 'Compassion-First Pet Hospitals', 'CHAIN',
     ['GENERAL_PRACTICE', 'EMERGENCY'], r'Compassion[- ]First', ''),
    (70, 'vetcor', 'VetCor', 'CHAIN',
     ['GENERAL_PRACTICE'], r'\bVetCor\b',
     'Almost always retains local brand — direct hits are rare.'),
    (80, 'thrive', 'Thrive Pet Healthcare', 'CHAIN',
     ['GENERAL_PRACTICE', 'SPECIALTY'], r'Thrive Pet', ''),
    (90, 'pathway', 'Pathway Vet Alliance', 'CHAIN',
     ['GENERAL_PRACTICE', 'SPECIALTY'], r'Pathway Vet', ''),
    (100, 'petvet', 'PetVet Care Centers', 'CHAIN',
     ['GENERAL_PRACTICE', 'SPECIALTY', 'EMERGENCY'], r'PetVet Care', ''),
    (110, 'vip_petcare', 'VIP Petcare', 'CHAIN',
     ['RETAIL_WELLNESS'], r'VIP Pet ?Care',
     'Walmart / Petco in-store wellness clinics.'),
    (120, 'vetco', 'Vetco / Vetco by Petco', 'RETAIL_EMBEDDED',
     ['RETAIL_WELLNESS'], r'\bVetco\b', 'Petco-operated.'),
    (130, 'medvet', 'MedVet', 'CHAIN',
     ['EMERGENCY', 'SPECIALTY'], r'\bMedVet\b', ''),
    (140, 'veg', 'Veterinary Emergency Group', 'CHAIN',
     ['EMERGENCY'], r'Veterinary Emergency Group',
     'Full name only; bare "VEG" collides with English words.'),
    (150, 'petwellclinic', 'PetWellClinic', 'FRANCHISE',
     ['URGENT_WELLNESS'], r'PetWell(Clinic)?',
     'Franchise; walk-in wellness only, no surgery/hospitalization.'),
    (160, 'heart_paw', 'Heart + Paw', 'CHAIN',
     ['GENERAL_PRACTICE', 'URGENT_CARE'], r'Heart\s*\+\s*Paw|Heart and Paw', ''),
    (170, 'petfolk', 'Petfolk', 'CHAIN',
     ['GENERAL_PRACTICE', 'TELE_VET'], r'\bPetfolk\b', ''),
    (180, 'modern_animal', 'Modern Animal', 'CHAIN',
     ['GENERAL_PRACTICE'], r'Modern Animal', 'Membership-based primary care.'),
    (190, 'bond_vet', 'Bond Vet', 'CHAIN',
     ['GENERAL_PRACTICE', 'URGENT_CARE'], r'Bond Vet', ''),
    (200, 'amerivet', 'AmeriVet', 'CHAIN',
     ['GENERAL_PRACTICE'], r'\bAmeriVet\b', ''),
]


def seed(apps, schema_editor):  # noqa: ARG001
    ChainKeyword = apps.get_model('hospital', 'ChainKeyword')
    if ChainKeyword.objects.exists():
        return
    ChainKeyword.objects.bulk_create([
        ChainKeyword(
            match_priority=priority,
            chain_brand_normalized=brand,
            display_name=display,
            ownership=ownership,
            service_tags=tags,
            regex_pattern=pattern,
            notes=notes or None,
        )
        for (priority, brand, display, ownership, tags, pattern, notes) in _SEED
    ])


def unseed(apps, schema_editor):  # noqa: ARG001
    ChainKeyword = apps.get_model('hospital', 'ChainKeyword')
    ChainKeyword.objects.filter(
        chain_brand_normalized__in=[row[1] for row in _SEED],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('hospital', '0006_drop_legacy_classification'),
    ]

    operations = [
        migrations.CreateModel(
            name='ChainKeyword',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('chain_brand_normalized', models.CharField(max_length=64, unique=True)),
                ('display_name', models.CharField(max_length=200)),
                ('ownership', models.CharField(max_length=32)),
                ('service_tags', django.contrib.postgres.fields.ArrayField(
                    base_field=models.CharField(max_length=32),
                    blank=True, default=list, size=None,
                )),
                ('regex_pattern', models.CharField(max_length=200)),
                ('match_priority', models.PositiveIntegerField(default=100)),
                ('notes', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'chain_keyword',
                'ordering': ['match_priority', 'id'],
            },
        ),
        migrations.RunPython(seed, reverse_code=unseed),
    ]

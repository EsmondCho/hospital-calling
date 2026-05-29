"""Demo seed for the public hospital-calling showcase.

Replaces the earlier dummy data (migration 0002) with a clean, self-contained
dataset a reviewer can explore end-to-end:

  * 10 INDEPENDENT hospitals across several US states, in the
    sourced-from-Google shape (real clinic names / cities / addresses).
  * 4 chain / retail hospitals (Mars VH / chain / retail) showing how the
    chain-keyword + Claude classification labels each clinic's ownership.
  * 1 mission prompt: ask a clinic for the earliest puppy-vaccination
    appointment within a week, with the patient (a puppy named Bella) baked in.
  * 2 PENDING call schedules, each fanning out to an ordered hospital
    sequence — the "campaign" view — with NO call attempts (the demo ships no
    real call recordings/transcripts; placing a live call needs a Bland.ai key).

Phone numbers are intentionally fictitious (the 555-01xx reserved range) so
that enabling Bland.ai and firing a schedule can never dial a real clinic.

The `ChainKeyword` table (seeded in hospital/0007) is left intact — it is the
regex rule set that drives chain labeling.
"""

from datetime import timedelta

from django.db import migrations
from django.utils import timezone


# (name, phone, formatted_address, city, state, postal, tz, service_tags, appt_mode)
INDEPENDENT = [
    ('All Pet Complex Veterinary Hospital', '+12085550101',
     '7660 N Horseshoe Bend Rd Suite 3, Boise, ID 83714, USA',
     'Boise', 'ID', '83714', 'America/Boise', ['GENERAL_PRACTICE'], 'APPOINTMENT_REQUIRED'),
    ('Hometown Animal Clinic', '+12085550102',
     '3500 W Overland Rd, Boise, ID 83705, USA',
     'Boise', 'ID', '83705', 'America/Boise', ['GENERAL_PRACTICE'], 'APPOINTMENT_REQUIRED'),
    ('Broadway Veterinary Hospital', '+12085550103',
     '2128 W University Dr, Boise, ID 83706, USA',
     'Boise', 'ID', '83706', 'America/Boise', ['GENERAL_PRACTICE'], 'APPOINTMENT_REQUIRED'),
    ('North Boise Veterinary Clinic', '+12085550110',
     '1003 N 28th St, Boise, ID 83702, USA',
     'Boise', 'ID', '83702', 'America/Boise', ['GENERAL_PRACTICE'], 'WALK_IN_ALLOWED'),
    ('Mac Rae Park Animal Hospital', '+15155550104',
     '2227 SW 9th St, Des Moines, IA 50315, USA',
     'Des Moines', 'IA', '50315', 'America/Chicago', ['GENERAL_PRACTICE'], 'APPOINTMENT_REQUIRED'),
    ('Lomas Veterinary Clinic', '+15055550105',
     '1100 Lomas Blvd NW Ste 2, Albuquerque, NM 87102, USA',
     'Albuquerque', 'NM', '87102', 'America/Denver', ['GENERAL_PRACTICE'], 'APPOINTMENT_REQUIRED'),
    ('East Valley Veterinary Clinic', '+18015550106',
     '2675 Parleys Way, Salt Lake City, UT 84109, USA',
     'Salt Lake City', 'UT', '84109', 'America/Denver', ['GENERAL_PRACTICE'], 'APPOINTMENT_REQUIRED'),
    ('Garland Animal Clinic', '+15095550107',
     '1022 W Garland Ave, Spokane, WA 99205, USA',
     'Spokane', 'WA', '99205', 'America/Los_Angeles', ['GENERAL_PRACTICE'], 'APPOINTMENT_REQUIRED'),
    ('Tender Care Veterinary Center', '+17195550108',
     '8036 Meridian Park Dr, Falcon, CO 80831, USA',
     'Falcon', 'CO', '80831', 'America/Denver', ['GENERAL_PRACTICE', 'EMERGENCY'], 'WALK_IN_ALLOWED'),
    ('Southpaw Veterinary Clinic and Emergency Care', '+14025550109',
     '19102 Q St Suite 115, Omaha, NE 68135, USA',
     'Omaha', 'NE', '68135', 'America/Chicago', ['GENERAL_PRACTICE', 'EMERGENCY'], 'WALK_IN_ALLOWED'),
]

# (name, phone, address, city, state, postal, tz, ownership, service_tags, excluded_reason)
EXCLUDED = [
    ('VCA Westside Animal Hospital', '+13105550111',
     '8500 Sepulveda Blvd, Los Angeles, CA 90045, USA',
     'Los Angeles', 'CA', '90045', 'America/Los_Angeles',
     'MARS_VH', ['GENERAL_PRACTICE'],
     'Matched chain keyword "VCA" → Mars Veterinary Health'),
    ('Banfield Pet Hospital', '+12085550113',
     '7319 W State St, Boise, ID 83714, USA',
     'Boise', 'ID', '83714', 'America/Boise',
     'MARS_VH', ['RETAIL_WELLNESS', 'GENERAL_PRACTICE'],
     'Matched chain keyword "Banfield" → Mars Veterinary Health (inside PetSmart)'),
    ('WestVet Boise 24/7 Animal Emergency & Specialty Center', '+12085550112',
     '5019 N Sawyer Ave, Garden City, ID 83714, USA',
     'Garden City', 'ID', '83714', 'America/Boise',
     'CHAIN', ['EMERGENCY', 'SPECIALTY'],
     'Multi-site emergency/specialty group'),
    ('VIP Petcare Vaccination Clinic', '+18005550114',
     '8300 W Overland Rd, Boise, ID 83709, USA',
     'Boise', 'ID', '83709', 'America/Boise',
     'RETAIL_EMBEDDED', ['RETAIL_WELLNESS'],
     'Matched chain keyword "VIP Petcare" → retail-embedded clinic'),
]

MISSION_BODY = """
You are an automated assistant calling a US veterinary clinic on behalf of a
pet owner, Dr.Tail. Your ONE goal is to find out the earliest appointment the
clinic can offer — within the next 7 days — for a puppy's vaccination booster.
Do not book anything. Just collect availability.

THE PATIENT
- Name: Bella
- Species/breed: dog, Golden Retriever
- Age: 14 weeks (puppy)
- Spayed/neutered: no (not yet)
- Reason for visit: second DHPP booster shot is due; owner also wants to ask
  about the rabies vaccine timing.

CALL OPENING (silence rule)
- Stay silent until a live human speaks. Do not talk over ringing, IVR menus,
  hold music, or voicemail. If a recorded greeting is followed by a human,
  start your introduction when the human comes on.

DISCLOSURE
- Open with: "Hi, I'm an automated assistant calling on behalf of a pet owner.
  This call may be recorded. I have a quick scheduling question about a puppy
  vaccination — do you have a moment?"
- If they decline, thank them and end.

THE QUESTION
- "We have a 14-week-old Golden Retriever puppy, Bella, due for her second
  DHPP booster. What's the earliest you could see her in the next week — and
  do you have any openings on a weekday morning?"
- If they offer a slot, repeat it back to confirm (day + time).
- If asked, mention she is not yet spayed and the owner also wants to discuss
  rabies vaccine timing.

WRAP-UP
- Note the earliest available day/time they give. Keep the call under
  2 minutes. Thank them and end. Do NOT confirm or book the appointment.

NEVER
- Pretend to be the pet owner or a human.
- Agree to or finalize a booking.
- Discuss pricing, referrals, or anything beyond appointment availability.
""".strip()

PATIENT = {
    'name': 'Bella',
    'species': 'dog',
    'breed': 'Golden Retriever',
    'age_weeks': 14,
    'life_stage': 'puppy',
    'spayed_neutered': False,
    'reason': 'second DHPP booster due; ask about rabies vaccine timing',
}


def seed(apps, schema_editor):  # noqa: ARG001
    Hospital = apps.get_model('hospital', 'Hospital')
    Prompt = apps.get_model('prompt', 'Prompt')
    CallSchedule = apps.get_model('calling', 'CallSchedule')
    CallAttempt = apps.get_model('calling', 'CallAttempt')
    CallScheduleHospital = apps.get_model('calling', 'CallScheduleHospital')

    # Start from a clean slate — drop whatever the older dummy seed created.
    # (ChainKeyword is left alone; it carries the chain-labeling rules.)
    CallScheduleHospital.objects.all().delete()
    CallAttempt.objects.all().delete()
    CallSchedule.objects.all().delete()
    Prompt.objects.all().delete()
    Hospital.objects.all().delete()

    independents = []
    for i, (name, phone, addr, city, state, postal, tz, tags, mode) in enumerate(INDEPENDENT, start=1):
        independents.append(Hospital(
            name=name, source='GOOGLE_PLACES', source_external_id=f'demo-ind-{i}',
            phone_e164=phone, formatted_address=addr, city=city, state=state,
            postal_code=postal, timezone=tz,
            ownership='INDEPENDENT', service_tags=tags, specialty_areas=[],
            appointment_mode=mode,
            metadata={'demo': True, 'classified_by': 'rule+llm'},
        ))
    Hospital.objects.bulk_create(independents)

    for i, (name, phone, addr, city, state, postal, tz, ownership, tags, reason) in enumerate(EXCLUDED, start=1):
        Hospital.objects.create(
            name=name, source='GOOGLE_PLACES', source_external_id=f'demo-exc-{i}',
            phone_e164=phone, formatted_address=addr, city=city, state=state,
            postal_code=postal, timezone=tz,
            ownership=ownership, service_tags=tags, specialty_areas=[],
            appointment_mode='UNKNOWN',
            excluded_reason=reason,
            metadata={'demo': True, 'classified_by': 'chain_keyword'},
        )

    mission = Prompt.objects.create(
        name='puppy-vaccination-availability',
        version=1,
        body=MISSION_BODY,
        notes='Demo mission — ask for the earliest puppy vaccination slot within 7 days.',
        metadata={'mission': 'appointment_availability', 'window_days': 7, 'patient': PATIENT},
    )

    # Re-fetch the saved independents in insertion order for stable targeting.
    saved = list(Hospital.objects.filter(ownership='INDEPENDENT').order_by('id'))
    now = timezone.now()

    # Campaign 1 — Boise puppy-vaccination sweep (first 3 Boise clinics).
    sched1 = CallSchedule.objects.create(
        prompt=mission,
        scheduled_at=now + timedelta(days=1),
        status='PENDING',
        memo='Demo campaign — Boise puppy vaccination sweep',
        voice='random', model='base',
        metadata={'demo': True},
    )
    for order, hosp in enumerate(saved[:3]):
        CallScheduleHospital.objects.create(
            schedule=sched1, hospital=hosp, order=order, status='PENDING',
        )

    # Campaign 2 — multi-state spillover (next 2 clinics).
    sched2 = CallSchedule.objects.create(
        prompt=mission,
        scheduled_at=now + timedelta(days=3),
        status='PENDING',
        memo='Demo campaign — multi-state spillover',
        voice='maya', model='base',
        metadata={'demo': True},
    )
    for order, hosp in enumerate(saved[4:6]):
        CallScheduleHospital.objects.create(
            schedule=sched2, hospital=hosp, order=order, status='PENDING',
        )


def unseed(apps, schema_editor):  # noqa: ARG001
    # Non-destructive reverse: clear the demo rows.
    for model_name in ('CallScheduleHospital', 'CallAttempt', 'CallSchedule'):
        apps.get_model('calling', model_name).objects.all().delete()
    apps.get_model('prompt', 'Prompt').objects.filter(
        name='puppy-vaccination-availability'
    ).delete()
    apps.get_model('hospital', 'Hospital').objects.filter(
        source_external_id__startswith='demo-'
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('calling', '0011_callcomment_author'),
        ('hospital', '0009_hospital_idx_hospital_phone'),
        ('prompt', '0006_alter_prompt_name'),
    ]

    operations = [
        migrations.RunPython(seed, reverse_code=unseed),
    ]

"""Seed dummy data so the backoffice has something to render before any real
calls have happened.

Inserts: 6 hospitals (mix of LOCAL / CHAIN / ER), 2 prompts (referral + pricing
v1, both active), 4 schedules (some PENDING, some DISPATCHED), and 4 call
attempts attached to the dispatched schedules — including one COMPLETED with a
fake transcript.

Idempotency: skips if hospitals already exist (anyone can rerun migrate).
"""

from datetime import timedelta

from django.db import migrations
from django.utils import timezone


REFERRAL_BODY = '''
You are calling a US local vet hospital. Your sole goal is to learn whether
the hospital has a referral fee / commission / rebate / discount arrangement
when an external service refers patients to them. Do NOT try to book.

Stay silent until a live human speaks. Open with: "Hi, I'm an automated
assistant calling from Dr.Tail. This call may be recorded. Do you have a
moment for one quick question about partner referrals?"

If they refuse, thank them and end. Otherwise ask: "If a service like ours
sent patients your way, do you have any kind of referral arrangement — a
fee, commission, rebate, or discount we could pass along to clients?"

Keep the call under 90 seconds.
'''.strip()

PRICING_BODY = '''
You are calling a US local vet hospital. Your sole goal is to collect typical
service prices for common treatments. Do NOT try to book.

Stay silent until a live human speaks. Open with: "Hi, I'm an automated
assistant calling from Dr.Tail. This call may be recorded. We're putting
together pricing information to share with pet owners — could you help me
with a couple of quick questions?"

Ask one at a time: wellness exam, core vaccinations, spay/neuter for a small
dog, basic dental cleaning, X-ray or basic blood panel.

Stop after 5 questions or 3 minutes. Thank them and end.
'''.strip()


def seed(apps, schema_editor):  # noqa: ARG001
    Hospital = apps.get_model('hospital', 'Hospital')
    Prompt = apps.get_model('prompt', 'Prompt')
    CallSchedule = apps.get_model('calling', 'CallSchedule')
    CallAttempt = apps.get_model('calling', 'CallAttempt')

    if Hospital.objects.exists():
        return

    hospitals = Hospital.objects.bulk_create([
        Hospital(
            name='Sunset Pet Hospital',
            source='MANUAL', source_external_id='dummy-1',
            phone_e164='+14155550101',
            formatted_address='1234 Sunset Blvd, San Francisco, CA 94110',
            city='San Francisco', state='CA', postal_code='94110',
            timezone='America/Los_Angeles',
            category='LOCAL', is_callable=True,
        ),
        Hospital(
            name='Greenwood Animal Clinic',
            source='MANUAL', source_external_id='dummy-2',
            phone_e164='+12065550102',
            formatted_address='5678 Pine Ave, Seattle, WA 98101',
            city='Seattle', state='WA', postal_code='98101',
            timezone='America/Los_Angeles',
            category='LOCAL', is_callable=True,
        ),
        Hospital(
            name='Lakeshore Veterinary',
            source='MANUAL', source_external_id='dummy-3',
            phone_e164='+13125550103',
            formatted_address='91 Lake Shore Dr, Chicago, IL 60611',
            city='Chicago', state='IL', postal_code='60611',
            timezone='America/Chicago',
            category='LOCAL', is_callable=True,
        ),
        Hospital(
            name='Brooklyn Heights Vet',
            source='MANUAL', source_external_id='dummy-4',
            phone_e164='+17185550104',
            formatted_address='200 Henry St, Brooklyn, NY 11201',
            city='Brooklyn', state='NY', postal_code='11201',
            timezone='America/New_York',
            category='LOCAL', is_callable=True,
        ),
        Hospital(
            name='VCA Westside Animal Hospital',
            source='MANUAL', source_external_id='dummy-5',
            phone_e164='+13105550105',
            formatted_address='8500 Sepulveda Blvd, Los Angeles, CA 90045',
            city='Los Angeles', state='CA', postal_code='90045',
            timezone='America/Los_Angeles',
            category='CHAIN', is_callable=False,
            excluded_reason='Chain (VCA)',
        ),
        Hospital(
            name='Citywide Pet Emergency',
            source='MANUAL', source_external_id='dummy-6',
            phone_e164='+12125550106',
            formatted_address='14 W 38th St, New York, NY 10018',
            city='New York', state='NY', postal_code='10018',
            timezone='America/New_York',
            category='ER_OR_URGENT', is_callable=False,
            excluded_reason='Emergency-only clinic',
        ),
    ])

    referral_prompt = Prompt.objects.create(
        name='referral-policy',
        objective='REFERRAL_POLICY',
        version=1,
        body=REFERRAL_BODY,
        language='en',
        is_active=True,
        notes='v1 seed — keep under 90s. See Linear DRT-5178 for design rules.',
    )
    pricing_prompt = Prompt.objects.create(
        name='pricing',
        objective='PRICING',
        version=1,
        body=PRICING_BODY,
        language='en',
        is_active=True,
        notes='v1 seed — 5 service categories. See Linear DRT-5178.',
    )

    callable_hospitals = [h for h in hospitals if h.is_callable]
    now = timezone.now()

    # 4 schedules: 2 dispatched (with attempts), 2 pending
    sched_dispatched_1 = CallSchedule.objects.create(
        hospital=callable_hospitals[0], prompt=referral_prompt,
        scheduled_at=now - timedelta(hours=2),
        status='DISPATCHED', label='dummy: referral, completed',
    )
    sched_dispatched_2 = CallSchedule.objects.create(
        hospital=callable_hospitals[1], prompt=pricing_prompt,
        scheduled_at=now - timedelta(hours=1, minutes=30),
        status='DISPATCHED', label='dummy: pricing, voicemail',
    )
    CallSchedule.objects.create(
        hospital=callable_hospitals[2], prompt=referral_prompt,
        scheduled_at=now + timedelta(hours=3),
        status='PENDING', label='dummy: referral, scheduled later today',
    )
    CallSchedule.objects.create(
        hospital=callable_hospitals[3], prompt=pricing_prompt,
        scheduled_at=now + timedelta(days=1),
        status='PENDING', label='dummy: pricing, tomorrow',
    )

    CallAttempt.objects.create(
        schedule=sched_dispatched_1,
        hospital=sched_dispatched_1.hospital,
        prompt=referral_prompt,
        blandai_call_id='dummy-call-aaaa-1111',
        status='COMPLETED',
        answered_by='HUMAN',
        call_ended_by='ASSISTANT',
        recording_url='https://example.com/dummy/recording-1.wav',
        started_at=now - timedelta(hours=2),
        ended_at=now - timedelta(hours=2) + timedelta(seconds=72),
        duration_seconds=72,
        summary=(
            'Front desk said they have no formal referral arrangement. '
            'Practice owner makes those decisions; offered to take a callback.'
        ),
        transcript=[
            {'user': 'assistant', 'text': "Hi, I'm an automated assistant calling from Dr.Tail. This call may be recorded. Do you have a moment for one quick question about partner referrals?"},
            {'user': 'user', 'text': 'Sure, what do you need?'},
            {'user': 'assistant', 'text': 'If a service like ours sent patients your way, do you have any kind of referral arrangement — a fee, commission, rebate, or discount we could pass along?'},
            {'user': 'user', 'text': "We don't really do that, no. The owner handles partnerships, you'd want to talk to her."},
            {'user': 'assistant', 'text': 'Got it — appreciate it. Thank you, have a good one.'},
        ],
        metadata={'cost_usd': 0.18, 'voice': 'maya'},
    )
    CallAttempt.objects.create(
        schedule=sched_dispatched_2,
        hospital=sched_dispatched_2.hospital,
        prompt=pricing_prompt,
        blandai_call_id='dummy-call-bbbb-2222',
        status='FAILED',
        answered_by='VOICEMAIL',
        recording_url='https://example.com/dummy/recording-2.wav',
        started_at=now - timedelta(hours=1, minutes=30),
        ended_at=now - timedelta(hours=1, minutes=30) + timedelta(seconds=18),
        duration_seconds=18,
        failure_reason='Voicemail picked up; AI ended call without leaving message.',
        transcript=[],
        metadata={'cost_usd': 0.04},
    )
    CallAttempt.objects.create(
        hospital=callable_hospitals[2],
        prompt=referral_prompt,
        blandai_call_id='dummy-call-cccc-3333',
        status='IN_PROGRESS',
        started_at=now - timedelta(minutes=2),
        metadata={},
    )
    CallAttempt.objects.create(
        hospital=callable_hospitals[3],
        prompt=pricing_prompt,
        blandai_call_id='dummy-call-dddd-4444',
        status='QUEUED',
        metadata={},
    )


def unseed(apps, schema_editor):  # noqa: ARG001
    # Reverse: delete dummy rows by external id markers
    Hospital = apps.get_model('hospital', 'Hospital')
    Prompt = apps.get_model('prompt', 'Prompt')
    CallAttempt = apps.get_model('calling', 'CallAttempt')
    CallSchedule = apps.get_model('calling', 'CallSchedule')

    CallAttempt.objects.filter(blandai_call_id__startswith='dummy-call-').delete()
    CallSchedule.objects.filter(label__startswith='dummy:').delete()
    Prompt.objects.filter(name__in=['referral-policy', 'pricing'], version=1).delete()
    Hospital.objects.filter(source='MANUAL', source_external_id__startswith='dummy-').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('hospital', '0001_initial'),
        ('prompt', '0001_initial'),
        ('calling', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed, reverse_code=unseed),
    ]

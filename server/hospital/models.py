from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models.functions import Upper

from hospital.vars import HospitalAppointmentMode, HospitalOwnership


class Hospital(models.Model):
    """A US vet hospital we may target for an HOSPCALL call."""

    name = models.CharField(max_length=200)

    # Sourcing
    source = models.CharField(max_length=32)              # see vars.HospitalSource
    source_external_id = models.CharField(max_length=128, null=True, blank=True)

    # Contact
    phone_e164 = models.CharField(max_length=24, null=True, blank=True)
    website = models.URLField(max_length=500, null=True, blank=True)

    # Address (US, free-form for now)
    formatted_address = models.CharField(max_length=500, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    state = models.CharField(max_length=2, null=True, blank=True)
    postal_code = models.CharField(max_length=16, null=True, blank=True)
    timezone = models.CharField(max_length=64, null=True, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # Classification (DRT-5204 §1). A campaign can scope targets by `ownership`.
    # `.value` (plain str) keeps the migration default a literal — passing
    # the enum member would couple migrations to the enum class.
    ownership = models.CharField(
        max_length=32, default=HospitalOwnership.UNCLASSIFIED.value,
    )                                                                     # see vars.HospitalOwnership
    service_tags = ArrayField(
        base_field=models.CharField(max_length=32),
        default=list,
        blank=True,
    )                                                                     # see vars.HospitalServiceTag
    # Specific specialty areas (e.g. 'cardiology', 'oncology', 'ophthalmology').
    # Only meaningful when SPECIALTY is among `service_tags`.
    specialty_areas = ArrayField(
        base_field=models.CharField(max_length=64),
        default=list,
        blank=True,
    )
    appointment_mode = models.CharField(
        max_length=32, default=HospitalAppointmentMode.UNKNOWN.value,
    )                                                                      # see vars.HospitalAppointmentMode

    # Label lock: set True when an operator hand-corrects this row in the
    # backoffice. The sourcing pipeline refuses to overwrite classification
    # fields on locked rows (DRT-5204 §B9).
    label_locked = models.BooleanField(default=False)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        db_constraint=False,
        on_delete=models.SET_NULL,
        related_name='+',
    )

    excluded_reason = models.CharField(max_length=200, null=True, blank=True)

    # Provider raw payload for later re-processing
    metadata = models.JSONField(default=dict)

    # Soft delete: backoffice DELETE flips this to True; lists/details
    # filter False and never see the row again. Real DB delete never happens
    # from the UI so historical relations stay intact.
    is_deleted = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'hospital'
        constraints = [
            models.UniqueConstraint(
                fields=['source', 'source_external_id'],
                name='uq_hospital_source_external',
                condition=models.Q(source_external_id__isnull=False),
            ),
        ]
        indexes = [
            models.Index(fields=['state'], name='idx_hospital_state'),
            # Functional index for case-insensitive state lookups — the
            # backoffice sourcing `/cities/` endpoint filters `state__iexact`.
            models.Index(Upper('state'), name='idx_hospital_state_upper'),
            models.Index(fields=['ownership'], name='idx_hospital_ownership'),
            GinIndex(fields=['service_tags'], name='idx_hospital_svctags_gin'),
            # Practice-dedup sibling lookup filters `phone_e164 = ? AND
            # is_deleted=false`. A plain index on phone is enough — the live
            # filter is selective via `is_deleted`'s own index.
            models.Index(fields=['phone_e164'], name='idx_hospital_phone'),
        ]

    def __str__(self) -> str:
        return f'Hospital #{self.id} {self.name}'


class ChainKeyword(models.Model):
    """A known US vet chain → default classification rule (DRT-5204 §3.2).

    The sourcing pipeline's rule pass (`match_chain`) matches a hospital's
    display name against every row's `regex_pattern` (case-insensitive);
    the first hit — lowest `match_priority` — seeds ownership +
    service_tags before the LLM second pass refines it.

    Read-only in the backoffice. Populate / tune via the Django admin
    console (`/admin/`) where regex precision can be hand-checked.
    """

    chain_brand_normalized = models.CharField(max_length=64, unique=True)
    display_name = models.CharField(max_length=200)
    ownership = models.CharField(max_length=32)            # see vars.HospitalOwnership
    service_tags = ArrayField(
        base_field=models.CharField(max_length=32),
        default=list,
        blank=True,
    )                                                       # see vars.HospitalServiceTag
    # Raw regex, compiled case-insensitively against the hospital name.
    regex_pattern = models.CharField(max_length=200)
    # Lower runs first — lets the operator order a specific pattern ahead
    # of a broader one when two could match the same name.
    match_priority = models.PositiveIntegerField(default=100)
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'chain_keyword'
        ordering = ['match_priority', 'id']

    def __str__(self) -> str:
        return f'ChainKeyword {self.chain_brand_normalized}'

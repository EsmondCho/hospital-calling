from rest_framework import serializers

from hospital.models import Hospital
from hospital.vars import HospitalSource


class HospitalLv1Serializer(serializers.ModelSerializer):
    # Total CallAttempt rows for this hospital — a query annotation set by
    # the list/detail views. `getattr` keeps a non-annotated instance
    # (e.g. a fresh POST/PATCH response) at 0 instead of raising.
    call_attempt_count = serializers.SerializerMethodField()

    def get_call_attempt_count(self, obj: Hospital) -> int:
        return getattr(obj, 'call_attempt_count', 0)

    class Meta:
        model = Hospital
        fields = [
            'id',
            'name',
            'call_attempt_count',
            # 3-axis classification (DRT-5204 §1).
            'ownership',
            'service_tags',
            'specialty_areas',
            'appointment_mode',
            'label_locked',
            'phone_e164',
            'city',
            'state',
            'timezone',
            'created_at',
        ]


class HospitalLv2Serializer(HospitalLv1Serializer):
    class Meta(HospitalLv1Serializer.Meta):
        fields = [
            *HospitalLv1Serializer.Meta.fields,
            'source',
            'source_external_id',
            'website',
            'formatted_address',
            'postal_code',
            'latitude',
            'longitude',
            'excluded_reason',
            'metadata',
            'reviewed_at',
            'reviewed_by',
            'updated_at',
        ]


class HospitalCreateSerializer(serializers.ModelSerializer):
    """Manual hospital entry / edit from the backoffice.

    `source` defaults to MANUAL. Operators may correct the classification
    fields directly; the view auto-sets `label_locked` on any write so the
    sourcing pipeline won't clobber the correction.
    """

    source = serializers.CharField(
        required=False, default=HospitalSource.MANUAL.value,
    )

    class Meta:
        model = Hospital
        fields = [
            'id',
            'name',
            'phone_e164',
            'website',
            'formatted_address',
            'city',
            'state',
            'postal_code',
            'timezone',
            'ownership',
            'service_tags',
            'specialty_areas',
            'appointment_mode',
            'label_locked',
            'source',
            'source_external_id',
            'metadata',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']

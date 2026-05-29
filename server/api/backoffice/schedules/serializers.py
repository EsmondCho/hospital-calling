from django.utils import timezone
from rest_framework import serializers

from calling.models import CallSchedule, CallScheduleHospital
from calling.vars import VOICE_CHOICES, CallModel, CallScheduleStatus
from hospital.models import Hospital


class CallScheduleTargetSerializer(serializers.ModelSerializer):
    """One hospital step inside a schedule's ordered dial sequence."""

    hospital_name = serializers.CharField(
        source='hospital.name', read_only=True, default=None
    )
    # Carried so the backoffice can render `scheduled_at` in the hospital's
    # local timezone without a round-trip per row (first target drives the UI).
    hospital_timezone = serializers.CharField(
        source='hospital.timezone', read_only=True, default=None
    )

    class Meta:
        model = CallScheduleHospital
        fields = [
            'hospital_id',
            'hospital_name',
            'hospital_timezone',
            'order',
            'status',
            'call_attempt_id',
        ]


class CallScheduleLv1Serializer(serializers.ModelSerializer):
    prompt_name = serializers.CharField(source='prompt.name', read_only=True, default=None)
    prompt_version = serializers.IntegerField(
        source='prompt.version', read_only=True, default=None
    )
    # Ordered hospital targets. The view prefetches `targets__hospital`, so
    # `hospital_count` reads the prefetched list rather than re-counting in SQL.
    targets = CallScheduleTargetSerializer(many=True, read_only=True)
    hospital_count = serializers.SerializerMethodField()

    class Meta:
        model = CallSchedule
        fields = [
            'id',
            'status',
            'scheduled_at',
            'memo',
            'voice',
            'model',
            'prompt_id',
            'prompt_name',
            'prompt_version',
            'hospital_count',
            'targets',
            'created_at',
        ]

    def get_hospital_count(self, obj) -> int:
        return len(obj.targets.all())


class CallScheduleLv2Serializer(CallScheduleLv1Serializer):
    class Meta(CallScheduleLv1Serializer.Meta):
        fields = [
            *CallScheduleLv1Serializer.Meta.fields,
            'metadata',
            'updated_at',
        ]


class CallScheduleCreateSerializer(serializers.ModelSerializer):
    """Inputs accepted from the backoffice when scheduling a call campaign.

    `hospitals` is an ordered id list — index = dial order. One schedule fans
    out to all of them sequentially. Required on create; on edit it's optional
    and, when present, replaces the target set (only reachable while PENDING).
    """

    # voice/model are constrained sets; the model column has no DB-level
    # choices (codebase convention), so the dropdown set is enforced here.
    voice = serializers.ChoiceField(choices=VOICE_CHOICES, required=False)
    model = serializers.ChoiceField(
        choices=[CallModel.BASE, CallModel.TURBO], required=False
    )
    hospitals = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
        allow_empty=False,
    )

    class Meta:
        model = CallSchedule
        fields = [
            'id',
            'hospitals',
            'prompt',
            'scheduled_at',
            'memo',
            'voice',
            'model',
            'metadata',
            'status',
            'created_at',
        ]
        read_only_fields = ['id', 'status', 'created_at']

    def validate_scheduled_at(self, value):
        # Backs both POST and PATCH — a past target would dispatch immediately
        # (or never), so reject it for create and edit alike.
        if value < timezone.now():
            raise serializers.ValidationError(
                'scheduled_at must be in the future.'
            )
        return value

    def validate_hospitals(self, value):
        # De-dupe but keep order (first occurrence wins) so a double-checked
        # hospital isn't dialed twice.
        seen: set[int] = set()
        ordered: list[int] = []
        for hid in value:
            if hid not in seen:
                seen.add(hid)
                ordered.append(hid)
        existing = set(
            Hospital.objects.filter(
                id__in=ordered, is_deleted=False
            ).values_list('id', flat=True)
        )
        missing = [hid for hid in ordered if hid not in existing]
        if missing:
            raise serializers.ValidationError(
                f'Unknown or deleted hospital ids: {missing}'
            )
        return ordered

    def validate(self, attrs):
        if self.instance is None and 'hospitals' not in attrs:
            raise serializers.ValidationError(
                {'hospitals': 'This field is required.'}
            )
        return attrs

    def _replace_targets(self, schedule, hospital_ids):
        CallScheduleHospital.objects.bulk_create(
            [
                CallScheduleHospital(
                    schedule=schedule, hospital_id=hid, order=i
                )
                for i, hid in enumerate(hospital_ids)
            ]
        )

    def create(self, validated_data):
        hospital_ids = validated_data.pop('hospitals')
        schedule = CallSchedule.objects.create(**validated_data)
        self._replace_targets(schedule, hospital_ids)
        return schedule

    def update(self, instance, validated_data):
        hospital_ids = validated_data.pop('hospitals', None)
        # Defense in depth: the detail view already 409s any edit once a
        # schedule leaves PENDING, but never let a target-set swap wipe
        # in-flight `CallScheduleHospital` rows (incl. a live DIALING step).
        if (
            hospital_ids is not None
            and instance.status != CallScheduleStatus.PENDING
        ):
            raise serializers.ValidationError(
                {'hospitals': 'Targets can only be changed while PENDING.'}
            )
        instance = super().update(instance, validated_data)
        if hospital_ids is not None:
            instance.targets.all().delete()
            self._replace_targets(instance, hospital_ids)
        return instance

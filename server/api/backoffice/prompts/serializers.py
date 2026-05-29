from django.db import IntegrityError, transaction
from rest_framework import serializers

from prompt.models import Prompt


class PromptListSerializer(serializers.Serializer):
    """One row per logical prompt for the aggregate list endpoint.

    Built from a `.values(...).annotate(...)` aggregate, not a `Prompt`
    instance — a logical prompt is the set of rows sharing `name`, so there
    is no single model row to bind a `ModelSerializer` to.
    """

    name = serializers.CharField()
    version_count = serializers.IntegerField()
    latest_version = serializers.IntegerField()
    updated_at = serializers.DateTimeField()


class PromptLv1Serializer(serializers.ModelSerializer):
    class Meta:
        model = Prompt
        fields = [
            'id',
            'name',
            'version',
            'updated_at',
        ]


class PromptLv2Serializer(PromptLv1Serializer):
    class Meta(PromptLv1Serializer.Meta):
        fields = [
            *PromptLv1Serializer.Meta.fields,
            'body',
            'notes',
            'metadata',
            'created_at',
        ]


class PromptVersionSerializer(PromptLv2Serializer):
    """A version row including `body` — used by the `versions/?name=` list.

    Identical field set to `PromptLv2Serializer`; kept as a named alias so
    the versions list and the single-version detail view can diverge later
    without disturbing each other.
    """


class PromptCreateSerializer(serializers.ModelSerializer):
    """Create or update a prompt version.

    On create, `version` auto-bumps to (current max for `name`) + 1 if
    omitted — an existing `name` makes a new version, a new `name` starts at
    version 1.
    """

    # Declared explicitly (not via `extra_kwargs`) so `required=False` actually
    # sticks — `extra_kwargs` was being shadowed by the auto-generated field
    # built from the non-null `PositiveIntegerField` model column.
    version = serializers.IntegerField(required=False)

    class Meta:
        model = Prompt
        fields = [
            'id',
            'name',
            'version',
            'body',
            'notes',
            'metadata',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        # `name` validators are cleared because multiple versions deliberately
        # share a `name`; uniqueness is `(name, version)`, enforced at the DB
        # level by the model constraint.
        extra_kwargs = {
            'name': {'validators': []},
        }
        # Drop DRF's auto-generated UniqueTogetherValidator(name, version):
        # it forces `version` back to required even when we declare it
        # optional, blocking the auto-bump path. Uniqueness is still enforced
        # at the DB level by the model constraint.
        validators = []

    def create(self, validated_data):
        with transaction.atomic():
            # `select_for_update()` locks the sibling rows for this `name` so
            # concurrent creates serialize — otherwise two requests can read
            # the same max version and collide on `uq_prompt_name_version`.
            last = (
                Prompt.objects.select_for_update()
                .filter(name=validated_data['name'])
                .order_by('-version')
                .first()
            )
            if 'version' not in validated_data:
                validated_data['version'] = (last.version + 1) if last else 1
            try:
                return Prompt.objects.create(**validated_data)
            except IntegrityError:
                # A concurrent create for a brand-new `name` can slip past the
                # (empty) select_for_update and collide on uq_prompt_name_version
                # — surface a clean 400 instead of an unhandled 500.
                raise serializers.ValidationError(
                    {'version': 'Concurrent version creation — please retry.'}
                )

    def update(self, instance, validated_data):
        with transaction.atomic():
            for field, value in validated_data.items():
                setattr(instance, field, value)
            instance.save()
            return instance

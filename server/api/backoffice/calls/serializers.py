from rest_framework import serializers

from calling.models import CallAttempt, CallComment


class CallAttemptLv1Serializer(serializers.ModelSerializer):
    hospital_name = serializers.CharField(source='hospital.name', read_only=True, default=None)
    prompt_name = serializers.CharField(source='prompt.name', read_only=True, default=None)
    prompt_version = serializers.IntegerField(
        source='prompt.version', read_only=True, default=None
    )
    # Annotated on the list queryset (no N+1); falls back to a COUNT for the
    # detail view, which doesn't annotate.
    comment_count = serializers.SerializerMethodField()

    class Meta:
        model = CallAttempt
        fields = [
            'id',
            'status',
            'answered_by',
            'duration_seconds',
            'started_at',
            'ended_at',
            'failure_reason',
            'hospital_id',
            'hospital_name',
            'prompt_id',
            'prompt_name',
            'prompt_version',
            'voice',
            'model',
            'blandai_call_id',
            'recording_url',
            'is_starred',
            'comment_count',
            'created_at',
        ]

    def get_comment_count(self, obj) -> int:
        annotated = getattr(obj, 'comment_count', None)
        return annotated if annotated is not None else obj.comments.count()


class CallAttemptLv2Serializer(CallAttemptLv1Serializer):
    class Meta(CallAttemptLv1Serializer.Meta):
        fields = [
            *CallAttemptLv1Serializer.Meta.fields,
            'call_ended_by',
            'summary',
            'transcript',
            'metadata',
            'schedule_id',
            'updated_at',
        ]


class CallAttemptStarSerializer(serializers.ModelSerializer):
    """PATCH /calls/<id>/ — toggle the operator star, nothing else."""

    class Meta:
        model = CallAttempt
        fields = ['id', 'is_starred']
        read_only_fields = ['id']


class CallCommentSerializer(serializers.ModelSerializer):
    """A call-log comment. `body` is the only client-writable field; `author`
    is set server-side from the authenticated backoffice user."""

    class Meta:
        model = CallComment
        fields = ['id', 'body', 'author', 'created_at', 'updated_at']
        read_only_fields = ['id', 'author', 'created_at', 'updated_at']

    def validate_body(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError('Comment body cannot be empty.')
        return value

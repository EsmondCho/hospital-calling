from django.conf import settings
from rest_framework import serializers

from sourcing.models import SourcingJob


class SourcingJobLv1Serializer(serializers.ModelSerializer):
    """List + table view fields."""

    class Meta:
        model = SourcingJob
        fields = [
            'id',
            'created_at',
            'state_code',
            'city',
            'status',
            'partial',
            'partial_reason',
            'total_tiles',
            'completed_tiles',
            'capped_tile_count',
            'failed_tile_count',
            'fetched_count',
            'inserted_count',
            'updated_count',
            'skipped_count',
            'excluded_count',
            'needs_review_count',
            'error_count',
            'actual_cost_usd',
        ]


class SourcingJobLv2Serializer(SourcingJobLv1Serializer):
    """Detail view — adds root viewport / guardrail / token fields."""

    class Meta(SourcingJobLv1Serializer.Meta):
        fields = [
            *SourcingJobLv1Serializer.Meta.fields,
            'triggered_by',
            'started_at',
            'completed_at',
            'error_message',
            'call_count',
            'max_depth',
            'call_limit',
            'root_south',
            'root_west',
            'root_north',
            'root_east',
            'llm_input_tokens',
            'llm_output_tokens',
        ]


class SourcingJobTriggerSerializer(serializers.Serializer):
    """`POST /backoffice/sourcing/jobs/` input.

    The operator supplies only the target region as text; the server
    resolves the viewport and recursively tiles it (DRT-5265). `max_depth`
    / `call_limit` are optional guardrail overrides — omitted values fall
    back to the settings defaults. Not a ModelSerializer so an operator
    can't accidentally submit `status` or `inserted_count`.
    """

    state_code = serializers.RegexField(regex=r'^[A-Z]{2}$', max_length=2)
    city = serializers.CharField(min_length=2, max_length=128, trim_whitespace=True)
    max_depth = serializers.IntegerField(
        min_value=1, max_value=8, required=False, default=settings.SOURCING_MAX_DEPTH,
    )
    call_limit = serializers.IntegerField(
        min_value=1, max_value=600, required=False, default=settings.SOURCING_CALL_LIMIT,
    )

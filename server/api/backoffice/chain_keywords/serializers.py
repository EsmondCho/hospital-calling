from rest_framework import serializers

from hospital.models import ChainKeyword


class ChainKeywordLv1Serializer(serializers.ModelSerializer):
    class Meta:
        model = ChainKeyword
        fields = [
            'id',
            'match_priority',
            'chain_brand_normalized',
            'display_name',
            'ownership',
            'service_tags',
            'regex_pattern',
            'notes',
            'created_at',
            'updated_at',
        ]

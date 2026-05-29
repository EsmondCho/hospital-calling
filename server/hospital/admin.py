from django.contrib import admin

from hospital.models import ChainKeyword


@admin.register(ChainKeyword)
class ChainKeywordAdmin(admin.ModelAdmin):
    """Console CRUD for the sourcing rule-pass chain table.

    The backoffice exposes this read-only; data entry happens here so
    regex patterns can be hand-tuned precisely.
    """

    list_display = (
        'match_priority',
        'chain_brand_normalized',
        'display_name',
        'ownership',
        'regex_pattern',
    )
    list_display_links = ('chain_brand_normalized',)
    ordering = ('match_priority', 'id')
    search_fields = ('chain_brand_normalized', 'display_name', 'regex_pattern')

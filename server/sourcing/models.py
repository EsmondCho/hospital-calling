from django.conf import settings
from django.db import models


class SourcingJob(models.Model):
    """A single run of the hospital sourcing pipeline (DRT-5204 §2, DRT-5265).

    Owned by the `sourcing` app. Holds:
      - the target region the operator picked (state + city text only),
      - the resolved root viewport the quadtree splits from,
      - lifecycle status, per-job counters streamed by the SSE endpoint,
      - tile-progress counters and partial-completion metadata,
      - actual cost / token tracking for the run.

    The per-tile search state lives on `SourcingTile` — see DRT-5265 §4.1.
    """

    created_at = models.DateTimeField(auto_now_add=True)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        db_constraint=False, on_delete=models.SET_NULL,
        related_name='+',
    )

    # Target region.
    state_code = models.CharField(max_length=2)
    city = models.CharField(max_length=128, null=True, blank=True)

    # Root viewport (resolved by `resolve_viewport`; duplicated on the root
    # SourcingTile — kept here for fast job-level lookup).
    root_south = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    root_west = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    root_north = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    root_east = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # Lifecycle.
    status = models.CharField(max_length=16, default='PENDING')   # see vars.SourcingJobStatus
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    # Counters streamed to the SSE progress UI.
    fetched_count = models.PositiveIntegerField(default=0)
    inserted_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)       # label-locked skip
    merged_count = models.PositiveIntegerField(default=0)        # practice-dedup merge into a sibling row
    excluded_count = models.PositiveIntegerField(default=0)      # rule-stage exclude
    needs_review_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)

    # Tile-progress counters (F() increments, streamed by SSE).
    total_tiles = models.PositiveIntegerField(default=0)         # cumulative discovered tiles
    completed_tiles = models.PositiveIntegerField(default=0)     # COMPLETED + SPLIT + FAILED
    capped_tile_count = models.PositiveIntegerField(default=0)   # capped_at_min_size=True tiles
    failed_tile_count = models.PositiveIntegerField(default=0)   # status=FAILED tiles
    call_count = models.PositiveIntegerField(default=0)          # Google searchText calls (guard)

    # Job parameter overrides (operator input; settings defaults copied at
    # trigger time). Literal defaults here so migrations don't serialize a
    # settings reference — settings defaults are applied in the serializer.
    max_depth = models.PositiveSmallIntegerField(default=6)
    call_limit = models.PositiveIntegerField(default=300)

    # Partial-completion metadata (research §Q7).
    partial = models.BooleanField(default=False)
    partial_reason = models.CharField(max_length=24, null=True, blank=True)  # see vars.PartialReason

    # Cost tracking (actuals, filled in as the run progresses).
    actual_cost_usd = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    llm_input_tokens = models.PositiveBigIntegerField(default=0)
    llm_output_tokens = models.PositiveBigIntegerField(default=0)

    class Meta:
        db_table = 'sourcing_job'
        indexes = [
            models.Index(fields=['status', '-created_at'], name='idx_sj_status_created'),
            models.Index(fields=['state_code', 'city', 'status'], name='idx_sj_loc_status'),
        ]

    def __str__(self) -> str:
        return f'SourcingJob #{self.pk} {self.state_code}/{self.city} {self.status}'


class City(models.Model):
    """US city reference data — every Census incorporated place / CDP plus
    New England towns, preloaded by the 0005 data migration. The backoffice
    sourcing form's city dropdown reads this table; the sourcing pipeline
    itself still resolves a city's search viewport from (state, name) via
    Google (DRT-5265 §4)."""

    state_code = models.CharField(max_length=2)
    name = models.CharField(max_length=128)

    class Meta:
        db_table = 'city'
        # The (state_code, name) unique index doubles as the lookup index
        # for the form's state-scoped city query (leading-column match).
        constraints = [
            models.UniqueConstraint(
                fields=['state_code', 'name'], name='uq_city_state_name',
            ),
        ]
        ordering = ['state_code', 'name']

    def __str__(self) -> str:
        return f'City {self.name}, {self.state_code}'


class SourcingTile(models.Model):
    """Quadtree tile — a search unit from recursively quartering a city
    viewport (DRT-5265 §4.1.2)."""

    job = models.ForeignKey(
        'SourcingJob', on_delete=models.CASCADE,
        related_name='tiles', db_constraint=False,
    )
    parent = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='children', db_constraint=False,
    )

    # Bounding box (rectangle). Google v1: low=SW corner, high=NE corner.
    south = models.DecimalField(max_digits=9, decimal_places=6)   # low.latitude
    west = models.DecimalField(max_digits=9, decimal_places=6)    # low.longitude
    north = models.DecimalField(max_digits=9, decimal_places=6)   # high.latitude
    east = models.DecimalField(max_digits=9, decimal_places=6)    # high.longitude

    depth = models.PositiveSmallIntegerField(default=0)           # root=0
    status = models.CharField(max_length=16, default='PENDING')   # see vars.SourcingTileStatus
    page_cursor = models.TextField(null=True, blank=True)         # per-tile cursor — race-free

    fetched_count = models.PositiveIntegerField(default=0)        # results this tile received
    page_count = models.PositiveSmallIntegerField(default=0)      # pages consumed (<=3)
    cost_usd = models.DecimalField(max_digits=8, decimal_places=4, default=0)

    capped_at_min_size = models.BooleanField(default=False)       # min-size + cap → potential miss
    error_message = models.TextField(null=True, blank=True)
    retry_count = models.PositiveSmallIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sourcing_tile'
        indexes = [
            models.Index(fields=['job', 'status'], name='idx_st_job_status'),
        ]

    def __str__(self) -> str:
        return f'SourcingTile #{self.pk} job={self.job_id} depth={self.depth} {self.status}'

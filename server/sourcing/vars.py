from utils.enums import StrEnum


class SourcingJobStatus(StrEnum):
    PENDING = 'PENDING'
    RUNNING = 'RUNNING'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'
    CANCELLED = 'CANCELLED'


class SourcingTileStatus(StrEnum):
    PENDING = 'PENDING'
    RUNNING = 'RUNNING'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'
    SPLIT = 'SPLIT'      # cap hit → split into 4 children; children carry the work


class PartialReason(StrEnum):
    CALL_LIMIT = 'call_limit'                # per-job Google call limit reached
    MIN_SIZE_RESIDUAL = 'min_size_residual'  # cap hit at min-size tile — potential miss
    TILE_FAILURES = 'tile_failures'          # >=1 tile failed after retries


# Statuses that should reject new triggers on the same (state, city) target.
ACTIVE_STATUSES: frozenset[str] = frozenset({
    SourcingJobStatus.PENDING,
    SourcingJobStatus.RUNNING,
})

# Statuses that mean the job is no longer running and Celery tasks should bail.
TERMINAL_STATUSES: frozenset[str] = frozenset({
    SourcingJobStatus.COMPLETED,
    SourcingJobStatus.FAILED,
    SourcingJobStatus.CANCELLED,
})

# Tile statuses that block job finalization (work still outstanding).
UNRESOLVED_TILE_STATUSES: frozenset[str] = frozenset({
    SourcingTileStatus.PENDING,
    SourcingTileStatus.RUNNING,
})

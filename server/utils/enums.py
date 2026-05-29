from __future__ import annotations

from enum import StrEnum as _StrEnum
from typing import Any


class StrEnum(_StrEnum):
    """Project StrEnum base — every domain enum inherits this.

    Kept in sync with mochii-server's `StrEnum` so the two backoffices
    share the same enum-handling conventions.
    """

    def __str__(self) -> str:
        return str(self.value)

    @classmethod
    def find(cls, value: Any) -> StrEnum | None:  # type: ignore[override]
        return cls(value) if value in cls._value2member_map_ else None

    @classmethod
    def get_vals(cls) -> list[str]:
        return [str(item) for item in cls]

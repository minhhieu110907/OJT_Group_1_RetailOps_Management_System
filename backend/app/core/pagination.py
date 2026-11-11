"""Framework-neutral pagination value objects shared by service ports."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Page[T]:
    """Immutable service-layer page matching the frozen Python contract."""

    items: tuple[T, ...]
    total: int
    page: int
    page_size: int

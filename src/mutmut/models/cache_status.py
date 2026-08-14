"""Cache status model for mutation testing results.

Defines the CacheStatus enum used to indicate whether a cached mutant result is
still valid, stale because a dependency changed, or invalid because the mutated
function itself changed.
"""

from __future__ import annotations

from enum import Enum


class CacheStatus(str, Enum):
    """Validity of a cached mutant result."""

    CACHED = "cached"  # tested, function unchanged
    STALE_DEPENDENCY = "stale"  # function unchanged but a dependency changed
    INVALID = "invalid"  # function changed (or untested), needs retest

    def __str__(self) -> str:
        return self.value

    def _severity(self) -> int:
        """Severity order: CACHED < STALE_DEPENDENCY < INVALID."""
        order = [CacheStatus.CACHED, CacheStatus.STALE_DEPENDENCY, CacheStatus.INVALID]
        return order.index(self)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, CacheStatus):
            return NotImplemented
        return self._severity() < other._severity()

    def __le__(self, other: object) -> bool:
        if not isinstance(other, CacheStatus):
            return NotImplemented
        return self._severity() <= other._severity()

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, CacheStatus):
            return NotImplemented
        return self._severity() > other._severity()

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, CacheStatus):
            return NotImplemented
        return self._severity() >= other._severity()

    def worst(self, other: CacheStatus) -> CacheStatus:
        """Return the worse (higher severity) of two statuses."""
        return self if self._severity() > other._severity() else other


CACHE_STATUS_EMOJI: dict[CacheStatus, str] = {
    CacheStatus.CACHED: "✓",
    CacheStatus.STALE_DEPENDENCY: "⚠️",
    CacheStatus.INVALID: "🚫",
}

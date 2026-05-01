"""Cache status model for mutation testing results.

This module defines the CacheStatus enum used to indicate whether
cached mutation test results are still valid.
"""

from enum import Enum


class CacheStatus(str, Enum):
    """Cache status for mutant results.

    Used to determine if a cached test result is still valid or needs retesting.
    """

    CACHED = "cached"  # ✓ — tested, function unchanged
    STALE_DEPENDENCY = "stale"  # ⚠️ — function unchanged but dependency changed
    INVALID = "invalid"  # 🚫 — function changed, needs retest

    def __str__(self) -> str:
        return self.value

    def _severity(self) -> int:
        """Return severity order: CACHED=0, STALE_DEPENDENCY=1, INVALID=2."""
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
        return self._severity() >= other._severity()

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, CacheStatus):
            return NotImplemented
        return self._severity() >= other._severity()

    def worst(self, other: "CacheStatus") -> "CacheStatus":
        """Return the worse of two statuses."""
        return self if self._severity() > other._severity() else other


CACHE_STATUS_EMOJI: dict[CacheStatus, str] = {
    CacheStatus.CACHED: "✓",
    CacheStatus.STALE_DEPENDENCY: "⚠️",
    CacheStatus.INVALID: "🚫",
}

"""Temporal tagging — computes staleness scores for chunks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.config.settings import get_settings
from src.models.schemas import Chunk


@dataclass(frozen=True)
class StalenessScore:
    score: float  # 0.0 (fresh) → 1.0 (very stale)
    reason: str


class TemporalTagger:
    """Assigns staleness scores to chunks based on age and related activity."""

    def __init__(self, threshold_days: int | None = None) -> None:
        self._threshold = threshold_days or get_settings().staleness_threshold_days

    def compute_staleness(
        self,
        chunk: Chunk,
        *,
        file_change_count: int = 0,
        has_superseding_content: bool = False,
    ) -> StalenessScore:
        """Return a *StalenessScore* for the given chunk.

        Parameters
        ----------
        chunk:
            The chunk to score.
        file_change_count:
            Number of times the referenced files have been modified since
            the chunk was created.
        has_superseding_content:
            Whether a newer document explicitly supersedes this chunk.
        """
        age = chunk.metadata.age_days
        age_factor = min(age / self._threshold, 1.0) if self._threshold > 0 else 0.0

        churn_factor = min(file_change_count / 50, 1.0) if file_change_count else 0.0

        supersede_factor = 0.5 if has_superseding_content else 0.0

        score = round(min(0.4 * age_factor + 0.35 * churn_factor + 0.25 * supersede_factor, 1.0), 3)

        reasons: list[str] = []
        if age > self._threshold:
            reasons.append(f"Content is {age} days old (threshold: {self._threshold})")
        if file_change_count > 0:
            reasons.append(f"Referenced files changed {file_change_count} times since creation")
        if has_superseding_content:
            reasons.append("Newer content explicitly supersedes this")

        return StalenessScore(
            score=score,
            reason="; ".join(reasons) if reasons else "Content appears current",
        )

    def tag_chunk(
        self,
        chunk: Chunk,
        *,
        file_change_count: int = 0,
        has_superseding_content: bool = False,
    ) -> Chunk:
        """Return a *copy* of *chunk* with staleness fields populated."""
        result = self.compute_staleness(
            chunk,
            file_change_count=file_change_count,
            has_superseding_content=has_superseding_content,
        )
        chunk.staleness_score = result.score
        chunk.staleness_reason = result.reason
        chunk.metadata.is_likely_outdated = result.score >= 0.6
        return chunk

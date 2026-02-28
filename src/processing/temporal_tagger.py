"""Temporal tagging — computes staleness scores for chunks.

This is the secret weapon over competitors.  If an architectural decision
was made and then the service was rewritten 6 months later, the old
decision is misleading if surfaced without context.

The staleness score combines three signals:
1. **Age** — how old is the content relative to the threshold?
2. **File churn** — how many times have the referenced files changed?
3. **Supersession** — is there newer content that explicitly replaces this?
"""

from __future__ import annotations

from dataclasses import dataclass

from src.config.settings import get_settings
from src.models.schemas import Chunk


@dataclass(frozen=True)
class StalenessScore:
    score: float  # 0.0 (fresh) → 1.0 (very stale)
    reason: str


# Default weights for combining the three signals.
_DEFAULT_AGE_WEIGHT = 0.4
_DEFAULT_CHURN_WEIGHT = 0.35
_DEFAULT_SUPERSEDE_WEIGHT = 0.25

# Number of file changes that maps to a churn_factor of 1.0
_CHURN_NORMALISER = 50

# Staleness threshold above which a chunk is flagged as "likely outdated"
_OUTDATED_THRESHOLD = 0.6


class TemporalTagger:
    """Assigns staleness scores to chunks based on age and related activity."""

    def __init__(
        self,
        threshold_days: int | None = None,
        *,
        age_weight: float = _DEFAULT_AGE_WEIGHT,
        churn_weight: float = _DEFAULT_CHURN_WEIGHT,
        supersede_weight: float = _DEFAULT_SUPERSEDE_WEIGHT,
        outdated_threshold: float = _OUTDATED_THRESHOLD,
    ) -> None:
        self._threshold = threshold_days if threshold_days is not None else get_settings().staleness_threshold_days
        self._age_w = age_weight
        self._churn_w = churn_weight
        self._supersede_w = supersede_weight
        self._outdated_threshold = outdated_threshold

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
            the chunk was created.  Must be >= 0.
        has_superseding_content:
            Whether a newer document explicitly supersedes this chunk.
        """
        if file_change_count < 0:
            raise ValueError("file_change_count must be non-negative")

        age = chunk.metadata.age_days
        age_factor = min(age / self._threshold, 1.0) if self._threshold > 0 else 0.0
        churn_factor = min(file_change_count / _CHURN_NORMALISER, 1.0) if file_change_count else 0.0
        supersede_factor = 0.5 if has_superseding_content else 0.0

        score = round(
            min(
                self._age_w * age_factor
                + self._churn_w * churn_factor
                + self._supersede_w * supersede_factor,
                1.0,
            ),
            3,
        )

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
        """Return *chunk* with staleness fields populated (mutates in-place)."""
        result = self.compute_staleness(
            chunk,
            file_change_count=file_change_count,
            has_superseding_content=has_superseding_content,
        )
        chunk.staleness_score = result.score
        chunk.staleness_reason = result.reason
        chunk.metadata.is_likely_outdated = result.score >= self._outdated_threshold
        return chunk

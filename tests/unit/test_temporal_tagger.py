"""Tests for the temporal tagger / staleness scoring."""

from __future__ import annotations

from src.models.schemas import Chunk, ChunkMetadata, SourceType
from src.processing.temporal_tagger import TemporalTagger


def _make_chunk(age_days: int = 0) -> Chunk:
    return Chunk(
        id="test-chunk",
        content="Some content",
        metadata=ChunkMetadata(
            source_type=SourceType.PR_DESCRIPTION,
            source_id="PR-1",
            age_days=age_days,
        ),
    )


class TestTemporalTagger:
    def setup_method(self):
        self.tagger = TemporalTagger(threshold_days=540)

    def test_fresh_content_has_low_staleness(self):
        chunk = _make_chunk(age_days=10)
        result = self.tagger.compute_staleness(chunk)
        assert result.score < 0.1

    def test_old_content_has_higher_staleness(self):
        chunk = _make_chunk(age_days=600)
        result = self.tagger.compute_staleness(chunk)
        assert result.score > 0.3

    def test_high_file_churn_increases_staleness(self):
        chunk = _make_chunk(age_days=100)
        result = self.tagger.compute_staleness(chunk, file_change_count=60)
        assert result.score > 0.3

    def test_superseding_content_increases_staleness(self):
        chunk = _make_chunk(age_days=100)
        result = self.tagger.compute_staleness(chunk, has_superseding_content=True)
        assert result.score >= 0.19

    def test_tag_chunk_sets_fields(self):
        chunk = _make_chunk(age_days=700)
        tagged = self.tagger.tag_chunk(chunk, file_change_count=100)
        assert tagged.staleness_score > 0
        assert tagged.staleness_reason != ""

    def test_very_stale_chunk_marked_outdated(self):
        chunk = _make_chunk(age_days=1000)
        tagged = self.tagger.tag_chunk(chunk, file_change_count=80, has_superseding_content=True)
        assert tagged.metadata.is_likely_outdated is True

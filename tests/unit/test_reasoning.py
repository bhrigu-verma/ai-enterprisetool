"""Tests for the reasoning engine helpers (no LLM calls)."""

from __future__ import annotations

from datetime import datetime, timezone

from src.models.schemas import Chunk, ChunkMetadata, QuestionType, SourceType
from src.reasoning.engine import (
    _compute_confidence,
    _extract_citations,
    _format_context,
    select_model,
)


def _make_chunk(
    source_type: SourceType = SourceType.PR_DESCRIPTION,
    source_id: str = "PR-1",
    staleness: float = 0.0,
    outdated: bool = False,
) -> Chunk:
    return Chunk(
        id="c1",
        content="chunk content",
        metadata=ChunkMetadata(
            source_type=source_type,
            source_id=source_id,
            is_likely_outdated=outdated,
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        ),
        staleness_score=staleness,
    )


class TestSelectModel:
    def test_complex_questions_use_opus(self):
        model = select_model(QuestionType.WHY)
        assert model  # non-empty

    def test_simple_questions_use_sonnet(self):
        model = select_model(QuestionType.GENERAL)
        assert model


class TestFormatContext:
    def test_format_includes_source_info(self):
        chunks = [_make_chunk(source_id="PR-42")]
        text = _format_context(chunks)
        assert "PR-42" in text
        assert "pr_description" in text

    def test_format_flags_outdated(self):
        chunks = [_make_chunk(staleness=0.8, outdated=True)]
        text = _format_context(chunks)
        assert "POSSIBLY OUTDATED" in text


class TestExtractCitations:
    def test_deduplicates_citations(self):
        chunks = [_make_chunk(source_id="PR-1"), _make_chunk(source_id="PR-1")]
        citations = _extract_citations(chunks)
        assert len(citations) == 1

    def test_multiple_sources(self):
        chunks = [
            _make_chunk(source_id="PR-1"),
            _make_chunk(source_type=SourceType.TICKET, source_id="ENG-100"),
        ]
        citations = _extract_citations(chunks)
        assert len(citations) == 2


class TestComputeConfidence:
    def test_empty_chunks_zero(self):
        assert _compute_confidence([]) == 0.0

    def test_fresh_diverse_chunks_high_confidence(self):
        chunks = [
            _make_chunk(source_type=SourceType.PR_DESCRIPTION, staleness=0.0),
            _make_chunk(source_type=SourceType.TICKET, staleness=0.1),
            _make_chunk(source_type=SourceType.SLACK_THREAD, staleness=0.05),
        ]
        conf = _compute_confidence(chunks)
        assert conf > 0.5

    def test_stale_chunks_lower_confidence(self):
        chunks = [_make_chunk(staleness=0.9)]
        conf = _compute_confidence(chunks)
        assert conf < 0.5

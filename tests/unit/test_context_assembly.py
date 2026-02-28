"""Tests for the context assembly engine."""

from __future__ import annotations

import pytest

from src.context_assembly.assembler import (
    ContextAssembler,
    classify_question,
    count_tokens,
    plan_retrieval,
)
from src.models.schemas import Chunk, ChunkMetadata, QuestionType, SourceType


def _make_chunk(
    source_type: SourceType = SourceType.PR_DESCRIPTION,
    content: str = "test content here",
    age_days: int = 0,
    staleness: float = 0.0,
) -> Chunk:
    return Chunk(
        id="c1",
        content=content,
        metadata=ChunkMetadata(
            source_type=source_type,
            source_id="X-1",
            age_days=age_days,
        ),
        staleness_score=staleness,
    )


class TestClassifyQuestion:
    def test_why_question(self):
        assert classify_question("Why was the payments service built this way?") == QuestionType.WHY

    def test_how_question(self):
        assert classify_question("How do I deploy the auth service?") == QuestionType.HOW

    def test_who_question(self):
        assert classify_question("Who is the owner of the billing repo?") == QuestionType.WHO

    def test_incident_question(self):
        assert classify_question("What broke in the last outage?") == QuestionType.WHAT_BROKE

    def test_general_question(self):
        assert classify_question("Tell me about the API") == QuestionType.GENERAL

    def test_empty_query_raises(self):
        with pytest.raises(ValueError):
            classify_question("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError):
            classify_question("   ")


class TestCountTokens:
    def test_empty_string(self):
        assert count_tokens("") == 0

    def test_non_empty(self):
        tokens = count_tokens("Hello, world!")
        assert tokens > 0


class TestRetrievalPlan:
    def test_why_plan_includes_decisions_sources(self):
        plan = plan_retrieval("why was X built?", QuestionType.WHY)
        assert SourceType.PR_DESCRIPTION in plan.source_type_filters
        assert SourceType.TICKET in plan.source_type_filters
        assert SourceType.SLACK_THREAD in plan.source_type_filters

    def test_how_plan_includes_code(self):
        plan = plan_retrieval("how to deploy?", QuestionType.HOW)
        assert SourceType.CODE in plan.source_type_filters


class TestContextAssembler:
    def test_assemble_filters_and_ranks(self):
        assembler = ContextAssembler(token_budget=100_000)
        chunks = [
            _make_chunk(SourceType.PR_DESCRIPTION, "PR about auth", age_days=10, staleness=0.1),
            _make_chunk(SourceType.SLACK_THREAD, "Slack about auth", age_days=5, staleness=0.05),
            _make_chunk(SourceType.CODE, "code snippet", age_days=1, staleness=0.0),
        ]
        result = assembler.assemble("why was auth built?", chunks)
        source_types = {c.metadata.source_type for c in result}
        assert SourceType.CODE not in source_types
        assert len(result) >= 1

    def test_assemble_respects_token_budget(self):
        assembler = ContextAssembler(token_budget=1)
        chunks = [_make_chunk(content="a " * 100)]  # many tokens
        result = assembler.assemble("tell me about X", chunks)
        assert len(result) == 0  # exceeds budget

    def test_assemble_empty_chunks(self):
        assembler = ContextAssembler()
        assert assembler.assemble("anything?", []) == []

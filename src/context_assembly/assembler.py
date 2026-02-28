"""Context assembly engine — query classification, retrieval planning, and token budget management."""

from __future__ import annotations

import logging
import re
from typing import Any

from src.config.settings import get_settings
from src.models.schemas import Chunk, QuestionType, RetrievalPlan, SourceType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Query classifier
# ---------------------------------------------------------------------------

_WHY_PATTERNS = re.compile(r"\b(why|reason|rationale|decision|chose|decided)\b", re.I)
_HOW_PATTERNS = re.compile(r"\b(how|implement|setup|configure|build|deploy)\b", re.I)
_WHO_PATTERNS = re.compile(r"\b(who|owner|maintainer|expert|knows|responsible)\b", re.I)
_INCIDENT_PATTERNS = re.compile(r"\b(broke|incident|outage|down|error|failure|bug)\b", re.I)


def classify_question(query: str) -> QuestionType:
    """Classify a natural-language query into a *QuestionType*."""
    if _WHY_PATTERNS.search(query):
        return QuestionType.WHY
    if _HOW_PATTERNS.search(query):
        return QuestionType.HOW
    if _WHO_PATTERNS.search(query):
        return QuestionType.WHO
    if _INCIDENT_PATTERNS.search(query):
        return QuestionType.WHAT_BROKE
    return QuestionType.GENERAL


# ---------------------------------------------------------------------------
# Retrieval planner
# ---------------------------------------------------------------------------

_QUESTION_SOURCE_MAP: dict[QuestionType, list[SourceType]] = {
    QuestionType.WHY: [
        SourceType.PR_DESCRIPTION,
        SourceType.TICKET,
        SourceType.SLACK_THREAD,
        SourceType.DOCUMENT,
    ],
    QuestionType.HOW: [
        SourceType.CODE,
        SourceType.DOCUMENT,
        SourceType.PR_DESCRIPTION,
        SourceType.COMMIT,
    ],
    QuestionType.WHO: [
        SourceType.PR_DESCRIPTION,
        SourceType.COMMIT,
        SourceType.SLACK_THREAD,
    ],
    QuestionType.WHAT_BROKE: [
        SourceType.SLACK_THREAD,
        SourceType.PR_DESCRIPTION,
        SourceType.TICKET,
    ],
    QuestionType.FACTUAL: [
        SourceType.DOCUMENT,
        SourceType.PR_DESCRIPTION,
    ],
    QuestionType.GENERAL: list(SourceType),
}


def plan_retrieval(query: str, question_type: QuestionType) -> RetrievalPlan:
    """Build a *RetrievalPlan* describing what sources to search."""
    return RetrievalPlan(
        question_type=question_type,
        vector_queries=[query],
        source_type_filters=_QUESTION_SOURCE_MAP.get(question_type, list(SourceType)),
    )


# ---------------------------------------------------------------------------
# Context assembler
# ---------------------------------------------------------------------------

class ContextAssembler:
    """Orchestrates query → retrieval plan → candidate ranking → token budgeting."""

    def __init__(self, token_budget: int | None = None) -> None:
        self._token_budget = token_budget or get_settings().max_context_tokens

    def assemble(self, query: str, candidate_chunks: list[Chunk]) -> list[Chunk]:
        """Return the best-fit set of chunks for *query* within the token budget."""
        question_type = classify_question(query)
        plan = plan_retrieval(query, question_type)
        filtered = self._apply_source_filter(candidate_chunks, plan)
        ranked = self._rank(filtered, question_type)
        return self._fit_to_budget(ranked)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_source_filter(chunks: list[Chunk], plan: RetrievalPlan) -> list[Chunk]:
        if not plan.source_type_filters:
            return chunks
        allowed = set(plan.source_type_filters)
        return [c for c in chunks if c.metadata.source_type in allowed]

    @staticmethod
    def _rank(chunks: list[Chunk], question_type: QuestionType) -> list[Chunk]:
        """Sort chunks by relevance heuristic: recency first, then staleness."""

        def _sort_key(c: Chunk) -> tuple[float, int]:
            # Lower staleness is better, more recent is better (higher age_days = worse)
            return (c.staleness_score, c.metadata.age_days)

        return sorted(chunks, key=_sort_key)

    def _fit_to_budget(self, chunks: list[Chunk]) -> list[Chunk]:
        """Greedily add chunks until the token budget is exhausted."""
        selected: list[Chunk] = []
        used = 0
        for chunk in chunks:
            tokens = _estimate_tokens(chunk.content)
            if used + tokens > self._token_budget:
                break
            selected.append(chunk)
            used += tokens
        return selected


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------

def _estimate_tokens(text: str) -> int:
    """Rough estimate: ~4 characters per token for English text."""
    return max(1, len(text) // 4)

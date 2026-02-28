"""Context assembly engine — query classification, retrieval planning, and token budget management.

This is the hardest engineering problem and the core of the product.
The naive approach (embed query → top-K chunks → stuff into context) fails
for complex questions.  Instead we:

1. Classify the question type (why / how / who / incident / general)
2. Build a retrieval plan that targets the right source types
3. Filter and rank candidates by recency + staleness
4. Fit into the token budget, preferring full documents over snippets
"""

from __future__ import annotations

import logging
import re

import tiktoken

from src.config.settings import get_settings
from src.models.schemas import Chunk, QuestionType, RetrievalPlan, SourceType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Token counting (using tiktoken for accuracy)
# ---------------------------------------------------------------------------

_tokenizer: tiktoken.Encoding | None = None


def _get_tokenizer() -> tiktoken.Encoding:
    global _tokenizer
    if _tokenizer is None:
        _tokenizer = tiktoken.get_encoding("cl100k_base")
    return _tokenizer


def count_tokens(text: str) -> int:
    """Count the number of tokens in *text*.

    Uses tiktoken when available; falls back to a character-based estimate
    (~4 characters per token) when the tokenizer cannot be loaded.
    """
    if not text:
        return 0
    try:
        return len(_get_tokenizer().encode(text))
    except Exception:
        # Fallback: ~4 characters per token for English text
        return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# Query classifier
# ---------------------------------------------------------------------------

_WHY_PATTERNS = re.compile(r"\b(why|reason|rationale|decision|chose|decided)\b", re.I)
_HOW_PATTERNS = re.compile(r"\b(how|implement|setup|configure|build|deploy)\b", re.I)
_WHO_PATTERNS = re.compile(r"\b(who|owner|maintainer|expert|knows|responsible)\b", re.I)
_INCIDENT_PATTERNS = re.compile(r"\b(broke|incident|outage|down|error|failure|bug)\b", re.I)


def classify_question(query: str) -> QuestionType:
    """Classify a natural-language query into a *QuestionType*.

    Raises *ValueError* if the query is empty.
    """
    if not query or not query.strip():
        raise ValueError("Query must not be empty")

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
        """Return the best-fit set of chunks for *query* within the token budget.

        Steps:
        1. Classify the question
        2. Filter by source type based on the retrieval plan
        3. Rank by staleness (freshest first)
        4. Greedily fill the token budget
        """
        if not candidate_chunks:
            return []

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
        """Sort chunks by relevance heuristic: lower staleness + newer is better."""

        def _sort_key(c: Chunk) -> tuple[float, int]:
            return (c.staleness_score, c.metadata.age_days)

        return sorted(chunks, key=_sort_key)

    def _fit_to_budget(self, chunks: list[Chunk]) -> list[Chunk]:
        """Greedily add chunks until the token budget is exhausted."""
        selected: list[Chunk] = []
        used = 0
        for chunk in chunks:
            tokens = count_tokens(chunk.content)
            if used + tokens > self._token_budget:
                break
            selected.append(chunk)
            used += tokens
        logger.debug(
            "Assembled %d chunks using %d tokens (budget: %d)",
            len(selected), used, self._token_budget,
        )
        return selected

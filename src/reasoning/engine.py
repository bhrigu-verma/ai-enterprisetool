"""Reasoning layer — LLM integration with streaming, citations, and confidence scoring.

Production-grade features:
- Model routing: complex questions → Opus, simple → Sonnet
- Configurable max_tokens and timeout
- Streaming with error handling
- Source citations extracted from assembled chunks
- Confidence scoring based on chunk quality and diversity
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from src.config.settings import get_settings
from src.models.schemas import (
    Chunk,
    QueryResponse,
    QuestionType,
    SourceCitation,
    SourceType,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_TEMPLATE = """\
You are an internal engineering assistant for {company_name}.
You have access to the company's entire engineering history:
PRs, tickets, Slack discussions, architecture docs, and incident reports.

When answering:
1. Always cite your sources (PR number, ticket ID, doc name, Slack date).
2. Flag if information might be outdated and why.
3. If you're uncertain, say so and explain what you'd need to be certain.
4. For "why" questions, trace the decision chain — what problem was being solved.
5. If multiple conflicting decisions exist, surface all of them with timestamps.

The current date is {date}. Information older than {staleness_threshold} days \
should be treated as potentially outdated unless confirmed by recent activity.
"""


def _build_system_prompt() -> str:
    settings = get_settings()
    return _SYSTEM_PROMPT_TEMPLATE.format(
        company_name=settings.company_name,
        date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        staleness_threshold=settings.staleness_threshold_days,
    )


# ---------------------------------------------------------------------------
# Query complexity routing
# ---------------------------------------------------------------------------

_COMPLEX_TYPES = {QuestionType.WHY, QuestionType.WHO, QuestionType.WHAT_BROKE}


def select_model(question_type: QuestionType) -> str:
    """Choose the LLM model based on query complexity."""
    settings = get_settings()
    if question_type in _COMPLEX_TYPES:
        return settings.opus_model
    return settings.sonnet_model


# ---------------------------------------------------------------------------
# Context formatting
# ---------------------------------------------------------------------------

def format_context(chunks: list[Chunk]) -> str:
    """Format chunks into a structured context block for the LLM."""
    parts: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        meta = chunk.metadata
        header = (
            f"[Source {i}] type={meta.source_type.value} id={meta.source_id} "
            f"author={meta.author} date={meta.timestamp}"
        )
        if chunk.staleness_score >= 0.6:
            header += f" ⚠ POSSIBLY OUTDATED ({chunk.staleness_reason})"
        parts.append(f"{header}\n{chunk.content}")
    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# Citation extraction
# ---------------------------------------------------------------------------

def extract_citations(chunks: list[Chunk]) -> list[SourceCitation]:
    """Deduplicate and return citations from the assembled chunks."""
    seen: set[str] = set()
    citations: list[SourceCitation] = []
    for chunk in chunks:
        key = chunk.metadata.source_id
        if key in seen:
            continue
        seen.add(key)
        citations.append(
            SourceCitation(
                source_type=chunk.metadata.source_type,
                source_id=chunk.metadata.source_id,
                timestamp=chunk.metadata.timestamp,
            )
        )
    return citations


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------

def compute_confidence(chunks: list[Chunk]) -> float:
    """Heuristic confidence score based on chunk quality and source diversity."""
    if not chunks:
        return 0.0
    avg_staleness = sum(c.staleness_score for c in chunks) / len(chunks)
    source_diversity = len({c.metadata.source_type for c in chunks}) / len(SourceType)
    return round(min(1.0, (1.0 - avg_staleness) * 0.7 + source_diversity * 0.3), 2)


# ---------------------------------------------------------------------------
# Reasoning engine
# ---------------------------------------------------------------------------

class ReasoningEngine:
    """Sends assembled context + query to the LLM and structures the response."""

    def __init__(self, anthropic_client: object | None = None) -> None:
        self._client = anthropic_client

    def _get_client(self):
        """Lazy-initialise the Anthropic client."""
        if self._client is None:
            import anthropic

            settings = get_settings()
            if not settings.anthropic_api_key:
                raise RuntimeError(
                    "Anthropic API key is not configured. "
                    "Set the AET_ANTHROPIC_API_KEY environment variable."
                )
            self._client = anthropic.AsyncAnthropic(
                api_key=settings.anthropic_api_key,
                timeout=settings.llm_timeout_seconds,
            )
        return self._client

    async def answer(
        self,
        query: str,
        chunks: list[Chunk],
        question_type: QuestionType = QuestionType.GENERAL,
    ) -> QueryResponse:
        """Generate a complete (non-streamed) response."""
        if not query or not query.strip():
            raise ValueError("Query must not be empty")

        settings = get_settings()
        model = select_model(question_type)
        system = _build_system_prompt()
        context = format_context(chunks)
        user_message = f"Context:\n{context}\n\nQuestion: {query}"

        client = self._get_client()
        message = await client.messages.create(
            model=model,
            max_tokens=settings.llm_max_output_tokens,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )

        answer_text = ""
        if message.content:
            answer_text = message.content[0].text

        staleness_warnings = [
            f"{c.metadata.source_id}: {c.staleness_reason}"
            for c in chunks
            if c.metadata.is_likely_outdated
        ]

        return QueryResponse(
            answer=answer_text,
            citations=extract_citations(chunks),
            confidence=compute_confidence(chunks),
            staleness_warnings=staleness_warnings,
            model_used=model,
        )

    async def answer_stream(
        self,
        query: str,
        chunks: list[Chunk],
        question_type: QuestionType = QuestionType.GENERAL,
    ) -> AsyncIterator[str]:
        """Yield streamed text tokens from the LLM.

        Handles mid-stream errors gracefully by logging and stopping the stream.
        """
        if not query or not query.strip():
            raise ValueError("Query must not be empty")

        settings = get_settings()
        model = select_model(question_type)
        system = _build_system_prompt()
        context = format_context(chunks)
        user_message = f"Context:\n{context}\n\nQuestion: {query}"

        client = self._get_client()
        try:
            async with client.messages.stream(
                model=model,
                max_tokens=settings.llm_max_output_tokens,
                system=system,
                messages=[{"role": "user", "content": user_message}],
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except Exception:
            logger.exception("Streaming error during LLM call")
            yield "\n\n[Error: streaming interrupted. Please try again.]"

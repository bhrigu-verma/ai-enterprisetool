"""Semantic chunking — splits content by meaningful boundaries, not character count."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from src.models.schemas import (
    Chunk,
    ChunkMetadata,
    CommitData,
    PRData,
    SlackThread,
    SourceType,
    TicketData,
)


class SemanticChunker:
    """Produces richly annotated :class:`Chunk` objects from ingested data."""

    # ------------------------------------------------------------------
    # PR chunking
    # ------------------------------------------------------------------

    def chunk_pr(self, pr: PRData) -> list[Chunk]:
        """Keep title+description as one chunk; each review comment is separate."""
        chunks: list[Chunk] = []

        # Main body
        body = f"PR #{pr.pr_id}: {pr.title}\n\n{pr.description}".strip()
        if body:
            chunks.append(
                Chunk(
                    id=_uid(),
                    content=body,
                    metadata=ChunkMetadata(
                        source_type=SourceType.PR_DESCRIPTION,
                        source_id=f"PR-{pr.pr_id}",
                        author=pr.author,
                        timestamp=pr.timestamp,
                        age_days=_age_days(pr.timestamp),
                        linked_entities=[f"ticket:{i}" for i in pr.linked_issues],
                        repo=pr.repo,
                    ),
                )
            )

        # Comments — one chunk each
        for idx, comment in enumerate(pr.comments):
            if not comment.strip():
                continue
            chunks.append(
                Chunk(
                    id=_uid(),
                    content=comment,
                    metadata=ChunkMetadata(
                        source_type=SourceType.PR_COMMENT,
                        source_id=f"PR-{pr.pr_id}-comment-{idx}",
                        author=pr.author,
                        timestamp=pr.timestamp,
                        age_days=_age_days(pr.timestamp),
                        repo=pr.repo,
                    ),
                )
            )

        return chunks

    # ------------------------------------------------------------------
    # Commit chunking
    # ------------------------------------------------------------------

    def chunk_commit(self, commit: CommitData) -> list[Chunk]:
        content = f"Commit {commit.sha[:8]}: {commit.message}"
        if commit.diff_summary:
            content += f"\n\nDiff summary:\n{commit.diff_summary}"
        return [
            Chunk(
                id=_uid(),
                content=content,
                metadata=ChunkMetadata(
                    source_type=SourceType.COMMIT,
                    source_id=commit.sha,
                    author=commit.author,
                    timestamp=commit.timestamp,
                    age_days=_age_days(commit.timestamp),
                    repo=commit.repo,
                ),
            )
        ]

    # ------------------------------------------------------------------
    # Slack thread chunking — keep whole thread as one chunk
    # ------------------------------------------------------------------

    def chunk_slack_thread(self, thread: SlackThread) -> list[Chunk]:
        if not thread.messages:
            return []
        content = "\n---\n".join(thread.messages)
        return [
            Chunk(
                id=_uid(),
                content=content,
                metadata=ChunkMetadata(
                    source_type=SourceType.SLACK_THREAD,
                    source_id=thread.thread_id,
                    author=", ".join(thread.participants),
                    timestamp=thread.timestamp,
                    age_days=_age_days(thread.timestamp),
                    tags=["slack"],
                ),
            )
        ]

    # ------------------------------------------------------------------
    # Ticket chunking — whole ticket as one chunk
    # ------------------------------------------------------------------

    def chunk_ticket(self, ticket: TicketData) -> list[Chunk]:
        content = f"[{ticket.ticket_id}] {ticket.title}\n\n{ticket.description}"
        return [
            Chunk(
                id=_uid(),
                content=content,
                metadata=ChunkMetadata(
                    source_type=SourceType.TICKET,
                    source_id=ticket.ticket_id,
                    author=ticket.assignee,
                    timestamp=ticket.timestamp,
                    age_days=_age_days(ticket.timestamp),
                    linked_entities=[f"pr:{p}" for p in ticket.linked_prs],
                    tags=ticket.labels,
                ),
            )
        ]

    # ------------------------------------------------------------------
    # Document chunking — split by H2/H3 sections
    # ------------------------------------------------------------------

    def chunk_document(
        self,
        text: str,
        *,
        doc_id: str = "",
        repo: str = "",
        author: str = "",
        timestamp: datetime | None = None,
    ) -> list[Chunk]:
        """Split a Markdown/text document by section headings."""
        sections = _split_by_headings(text)
        return [
            Chunk(
                id=_uid(),
                content=section,
                metadata=ChunkMetadata(
                    source_type=SourceType.DOCUMENT,
                    source_id=doc_id,
                    author=author,
                    timestamp=timestamp,
                    age_days=_age_days(timestamp),
                    repo=repo,
                ),
            )
            for section in sections
            if section.strip()
        ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return uuid.uuid4().hex


def _age_days(ts: datetime | None) -> int:
    if ts is None:
        return 0
    now = datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return max(0, (now - ts).days)


def _split_by_headings(text: str) -> list[str]:
    """Split Markdown text at ``##`` or ``###`` headings."""
    parts = re.split(r"(?m)^(#{2,3}\s)", text)
    if len(parts) <= 1:
        return [text] if text.strip() else []
    # Re-join heading markers with their content
    sections: list[str] = []
    if parts[0].strip():
        sections.append(parts[0])
    for i in range(1, len(parts) - 1, 2):
        sections.append(parts[i] + parts[i + 1])
    return sections

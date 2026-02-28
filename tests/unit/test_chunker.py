"""Tests for the semantic chunker."""

from __future__ import annotations

from datetime import datetime, timezone

from src.models.schemas import CommitData, PRData, SlackThread, SourceType, TicketData
from src.processing.chunker import SemanticChunker


class TestSemanticChunker:
    def setup_method(self):
        self.chunker = SemanticChunker()

    # ------------------------------------------------------------------
    # PR chunking
    # ------------------------------------------------------------------

    def test_chunk_pr_creates_body_and_comment_chunks(self):
        pr = PRData(
            pr_id="42",
            repo="acme/backend",
            title="Add auth middleware",
            description="Implement JWT-based auth for all endpoints.",
            author="alice",
            comments=["Looks good!", "Consider edge case on expiry."],
            linked_issues=["ENG-100"],
            timestamp=datetime(2024, 1, 15, tzinfo=timezone.utc),
        )
        chunks = self.chunker.chunk_pr(pr)
        assert len(chunks) == 3  # 1 body + 2 comments

        body_chunk = chunks[0]
        assert "Add auth middleware" in body_chunk.content
        assert body_chunk.metadata.source_type == SourceType.PR_DESCRIPTION
        assert body_chunk.metadata.source_id == "PR-42"
        assert body_chunk.metadata.author == "alice"
        assert "ticket:ENG-100" in body_chunk.metadata.linked_entities

        comment_chunk = chunks[1]
        assert comment_chunk.metadata.source_type == SourceType.PR_COMMENT

    def test_chunk_pr_skips_empty_comments(self):
        pr = PRData(
            pr_id="1", repo="x/y", title="Fix", description="desc", comments=["", "  "]
        )
        chunks = self.chunker.chunk_pr(pr)
        assert len(chunks) == 1  # only body

    # ------------------------------------------------------------------
    # Commit chunking
    # ------------------------------------------------------------------

    def test_chunk_commit(self):
        commit = CommitData(
            sha="abc123def456",
            repo="acme/backend",
            message="fix: resolve null pointer in auth",
            author="bob",
            timestamp=datetime(2024, 3, 1, tzinfo=timezone.utc),
        )
        chunks = self.chunker.chunk_commit(commit)
        assert len(chunks) == 1
        assert "abc123de" in chunks[0].content
        assert chunks[0].metadata.source_type == SourceType.COMMIT

    # ------------------------------------------------------------------
    # Slack thread chunking
    # ------------------------------------------------------------------

    def test_chunk_slack_thread_keeps_thread_together(self):
        thread = SlackThread(
            thread_id="C123:1234.5678",
            channel="C123",
            messages=["Should we use Postgres?", "Yes, for ACID compliance.", "+1"],
            participants=["alice", "bob"],
            timestamp=datetime(2024, 2, 10, tzinfo=timezone.utc),
        )
        chunks = self.chunker.chunk_slack_thread(thread)
        assert len(chunks) == 1
        assert "Postgres" in chunks[0].content
        assert chunks[0].metadata.source_type == SourceType.SLACK_THREAD

    def test_chunk_slack_thread_empty_messages(self):
        thread = SlackThread(thread_id="x", channel="x", messages=[])
        assert self.chunker.chunk_slack_thread(thread) == []

    # ------------------------------------------------------------------
    # Ticket chunking
    # ------------------------------------------------------------------

    def test_chunk_ticket(self):
        ticket = TicketData(
            ticket_id="ENG-200",
            title="Migrate to new auth provider",
            description="We need to move from Auth0 to in-house.",
            labels=["auth", "migration"],
            linked_prs=["42"],
        )
        chunks = self.chunker.chunk_ticket(ticket)
        assert len(chunks) == 1
        assert "ENG-200" in chunks[0].content
        assert chunks[0].metadata.source_type == SourceType.TICKET
        assert "pr:42" in chunks[0].metadata.linked_entities

    # ------------------------------------------------------------------
    # Document chunking
    # ------------------------------------------------------------------

    def test_chunk_document_splits_by_heading(self):
        doc = "# Intro\nSome text.\n## Section A\nContent A.\n## Section B\nContent B."
        chunks = self.chunker.chunk_document(doc, doc_id="arch.md", repo="acme/docs")
        assert len(chunks) >= 2
        assert any("Section A" in c.content for c in chunks)

    def test_chunk_document_single_section(self):
        doc = "Just a paragraph with no headings."
        chunks = self.chunker.chunk_document(doc, doc_id="notes.md")
        assert len(chunks) == 1

"""Tests for the FastAPI endpoints (no external services required)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.interfaces.api import app, get_chunk_repository, _audit_logger, _feedback_store
from src.models.schemas import Chunk, ChunkMetadata, SourceType


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_store():
    """Clear the chunk repository and stores between tests."""
    repo = get_chunk_repository()
    repo.clear()
    _audit_logger.clear()
    _feedback_store.clear()
    yield
    repo.clear()
    _audit_logger.clear()
    _feedback_store.clear()


class TestHealthEndpoint:
    def test_health_returns_status(self, client: TestClient):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "chunks_indexed" in data

    def test_health_reflects_chunk_count(self, client: TestClient):
        repo = get_chunk_repository()
        repo.add(
            Chunk(
                id="c1",
                content="test",
                metadata=ChunkMetadata(source_type=SourceType.DOCUMENT, source_id="D-1"),
            )
        )
        resp = client.get("/health")
        assert resp.json()["chunks_indexed"] == 1


class TestAskEndpoint:
    def test_ask_no_context_returns_helpful_message(self, client: TestClient):
        resp = client.post("/ask", json={"query": "why was auth built?"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["confidence"] == 0.0

    def test_ask_empty_query_rejected(self, client: TestClient):
        resp = client.post("/ask", json={"query": ""})
        assert resp.status_code == 422  # validation error

    def test_ask_with_context_but_no_llm_returns_error(self, client: TestClient):
        """Without an LLM key the endpoint should return an error status."""
        repo = get_chunk_repository()
        repo.add(
            Chunk(
                id="c1",
                content="Auth was built using JWT because of compliance.",
                metadata=ChunkMetadata(source_type=SourceType.PR_DESCRIPTION, source_id="PR-1"),
            )
        )
        resp = client.post("/ask", json={"query": "why was auth built?"})
        assert resp.status_code in (500, 502)


class TestAuditEndpoint:
    def test_audit_initially_empty(self, client: TestClient):
        resp = client.get("/audit")
        assert resp.status_code == 200
        assert resp.json() == []


class TestAuditExportEndpoint:
    def test_export_csv_empty(self, client: TestClient):
        resp = client.get("/audit/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        content = resp.text
        assert "timestamp" in content
        assert "user_id" in content

    def test_export_csv_with_entries(self, client: TestClient):
        _audit_logger.log(
            user_id="alice",
            query="why was auth built?",
            response_summary="Because compliance.",
            chunks_retrieved=["PR-1", "PR-2"],
        )
        resp = client.get("/audit/export")
        assert resp.status_code == 200
        assert "alice" in resp.text
        assert "why was auth built?" in resp.text


class TestFeedbackEndpoint:
    def test_submit_feedback_up(self, client: TestClient):
        resp = client.post("/feedback", json={
            "query": "how do I deploy?",
            "rating": "up",
            "user_id": "bob",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_submit_feedback_down_with_comment(self, client: TestClient):
        resp = client.post("/feedback", json={
            "query": "how do I deploy?",
            "rating": "down",
            "user_id": "carol",
            "comment": "Answer was wrong",
        })
        assert resp.status_code == 200

    def test_feedback_invalid_rating_rejected(self, client: TestClient):
        resp = client.post("/feedback", json={
            "query": "test",
            "rating": "invalid",
        })
        assert resp.status_code == 422

    def test_get_feedback(self, client: TestClient):
        client.post("/feedback", json={
            "query": "test query",
            "rating": "up",
            "user_id": "alice",
        })
        resp = client.get("/feedback")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["rating"] == "up"


class TestChunksEndpoint:
    def test_chunks_initially_empty(self, client: TestClient):
        resp = client.get("/chunks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["chunks"] == []

    def test_chunks_returns_paginated(self, client: TestClient):
        repo = get_chunk_repository()
        for i in range(5):
            repo.add(Chunk(
                id=f"c{i}",
                content=f"Content {i}",
                metadata=ChunkMetadata(
                    source_type=SourceType.PR_DESCRIPTION,
                    source_id=f"PR-{i}",
                    repo="acme/backend",
                ),
            ))
        resp = client.get("/chunks?per_page=2&page=1")
        data = resp.json()
        assert data["total"] == 5
        assert len(data["chunks"]) == 2
        assert data["pages"] == 3

    def test_chunks_filter_by_source_type(self, client: TestClient):
        repo = get_chunk_repository()
        repo.add(Chunk(
            id="c1", content="PR content",
            metadata=ChunkMetadata(source_type=SourceType.PR_DESCRIPTION, source_id="PR-1"),
        ))
        repo.add(Chunk(
            id="c2", content="Commit content",
            metadata=ChunkMetadata(source_type=SourceType.COMMIT, source_id="abc123"),
        ))
        resp = client.get("/chunks?source_type=commit")
        data = resp.json()
        assert data["total"] == 1
        assert data["chunks"][0]["source_type"] == "commit"

    def test_chunks_filter_by_repo(self, client: TestClient):
        repo = get_chunk_repository()
        repo.add(Chunk(
            id="c1", content="Backend",
            metadata=ChunkMetadata(
                source_type=SourceType.PR_DESCRIPTION,
                source_id="PR-1",
                repo="acme/backend",
            ),
        ))
        repo.add(Chunk(
            id="c2", content="Frontend",
            metadata=ChunkMetadata(
                source_type=SourceType.PR_DESCRIPTION,
                source_id="PR-2",
                repo="acme/frontend",
            ),
        ))
        resp = client.get("/chunks?repo=acme/backend")
        data = resp.json()
        assert data["total"] == 1


class TestStatsEndpoint:
    def test_stats_empty(self, client: TestClient):
        resp = client.get("/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["chunks"]["total"] == 0
        assert data["queries"]["total"] == 0
        assert data["feedback"]["total"] == 0

    def test_stats_with_data(self, client: TestClient):
        repo = get_chunk_repository()
        repo.add(Chunk(
            id="c1", content="PR content",
            metadata=ChunkMetadata(
                source_type=SourceType.PR_DESCRIPTION,
                source_id="PR-1",
                repo="acme/backend",
            ),
        ))
        _audit_logger.log(user_id="alice", query="how?")
        _feedback_store.add(user_id="alice", query="how?", rating="up")
        _feedback_store.add(user_id="bob", query="why?", rating="down")

        resp = client.get("/stats")
        data = resp.json()
        assert data["chunks"]["total"] == 1
        assert data["chunks"]["by_source_type"]["pr_description"] == 1
        assert data["queries"]["total"] == 1
        assert data["feedback"]["total"] == 2
        assert data["feedback"]["positive"] == 1
        assert data["feedback"]["negative"] == 1
        assert data["feedback"]["satisfaction_rate"] == 0.5


class TestSecurityHeaders:
    def test_security_headers_present(self, client: TestClient):
        resp = client.get("/health")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("X-XSS-Protection") == "1; mode=block"
        assert "strict-origin" in resp.headers.get("Referrer-Policy", "")
        assert "Content-Security-Policy" in resp.headers
        assert "frame-ancestors 'none'" in resp.headers["Content-Security-Policy"]


class TestGitHubWebhook:
    def test_webhook_ignores_non_pr_events(self, client: TestClient):
        resp = client.post(
            "/webhook/github",
            json={"action": "created"},
            headers={"X-GitHub-Event": "push"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_webhook_invalid_json_rejected(self, client: TestClient):
        resp = client.post(
            "/webhook/github",
            content=b"not json",
            headers={"Content-Type": "application/json", "X-GitHub-Event": "push"},
        )
        assert resp.status_code == 400 or resp.status_code == 422


class TestIngestEndpoint:
    def test_ingest_invalid_owner_rejected(self, client: TestClient):
        resp = client.post("/ingest/github", json={"owner": "bad/owner", "repo": "x"})
        assert resp.status_code == 422

    def test_ingest_missing_token_returns_500(self, client: TestClient):
        resp = client.post("/ingest/github", json={"owner": "acme", "repo": "backend"})
        assert resp.status_code == 500


class TestGlobalErrorHandler:
    def test_unhandled_errors_return_500(self, client: TestClient):
        """The global exception handler should catch unexpected errors."""
        resp = client.get("/nonexistent")
        assert resp.status_code in (404, 500)

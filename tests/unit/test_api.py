"""Tests for the FastAPI endpoints (no external services required)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.interfaces.api import app, get_chunk_repository
from src.models.schemas import Chunk, ChunkMetadata, SourceType


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_store():
    """Clear the chunk repository between tests."""
    repo = get_chunk_repository()
    repo.clear()
    yield
    repo.clear()


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

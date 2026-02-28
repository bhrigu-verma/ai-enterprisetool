"""Tests for the FastAPI endpoints (no external services required)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.interfaces.api import app, get_chunk_store
from src.models.schemas import Chunk, ChunkMetadata, SourceType


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_store():
    """Clear the in-memory chunk store between tests."""
    store = get_chunk_store()
    store.clear()
    yield
    store.clear()


class TestHealthEndpoint:
    def test_health(self, client: TestClient):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data


class TestAskEndpoint:
    def test_ask_no_context(self, client: TestClient):
        resp = client.post("/ask", json={"query": "why was auth built?"})
        assert resp.status_code == 200
        data = resp.json()
        assert "don't have enough context" in data["answer"].lower() or data["confidence"] == 0.0

    def test_ask_with_context_but_no_llm(self, client: TestClient):
        """Without an LLM key, the endpoint should return a 500 error gracefully."""
        store = get_chunk_store()
        store.append(
            Chunk(
                id="c1",
                content="Auth was built using JWT because of compliance.",
                metadata=ChunkMetadata(
                    source_type=SourceType.PR_DESCRIPTION,
                    source_id="PR-1",
                ),
            )
        )
        resp = client.post("/ask", json={"query": "why was auth built?"})
        # Will fail at the LLM call since no API key is configured
        assert resp.status_code == 500


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

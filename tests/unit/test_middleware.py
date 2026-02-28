"""Tests for middleware — API key auth, rate limiting, request logging."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from src.config.settings import reset_settings
from src.interfaces.api import app


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


class TestAPIKeyMiddleware:
    def test_public_endpoints_skip_auth(self, client: TestClient):
        """Health and docs should be accessible without an API key."""
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_no_keys_configured_allows_all(self, client: TestClient):
        """When no API keys are set, all requests pass (dev mode)."""
        resp = client.get("/audit")
        assert resp.status_code == 200

    def test_with_keys_configured_rejects_unauthenticated(self, client: TestClient):
        """When keys are configured, requests without a key are rejected."""
        os.environ["AET_API_KEYS"] = '["test-key-123"]'
        reset_settings()
        try:
            resp = client.get("/audit")
            assert resp.status_code == 401
            assert "Invalid or missing API key" in resp.json()["detail"]
        finally:
            os.environ.pop("AET_API_KEYS", None)
            reset_settings()

    def test_with_valid_key_allows_access(self, client: TestClient):
        """A valid API key should grant access."""
        os.environ["AET_API_KEYS"] = '["test-key-123"]'
        reset_settings()
        try:
            resp = client.get("/audit", headers={"X-API-Key": "test-key-123"})
            assert resp.status_code == 200
        finally:
            os.environ.pop("AET_API_KEYS", None)
            reset_settings()

    def test_webhooks_skip_api_key_auth(self, client: TestClient):
        """Webhook endpoints authenticate via signature, not API key."""
        os.environ["AET_API_KEYS"] = '["test-key-123"]'
        reset_settings()
        try:
            resp = client.post(
                "/webhook/github",
                json={"action": "push"},
                headers={"X-GitHub-Event": "push"},
            )
            assert resp.status_code == 200
        finally:
            os.environ.pop("AET_API_KEYS", None)
            reset_settings()

"""Tests for middleware — API key auth, rate limiting, security headers, request logging."""

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

    def test_static_files_skip_auth(self, client: TestClient):
        """Static file paths should not require API keys."""
        os.environ["AET_API_KEYS"] = '["test-key-123"]'
        reset_settings()
        try:
            resp = client.get("/static/styles.css")
            # Should not be 401; 200 or 404 is fine depending on file existence
            assert resp.status_code != 401
        finally:
            os.environ.pop("AET_API_KEYS", None)
            reset_settings()


class TestSecurityHeadersMiddleware:
    def test_csp_header_present(self, client: TestClient):
        resp = client.get("/health")
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp

    def test_xframe_options(self, client: TestClient):
        resp = client.get("/health")
        assert resp.headers.get("X-Frame-Options") == "DENY"

    def test_nosniff(self, client: TestClient):
        resp = client.get("/health")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"

    def test_referrer_policy(self, client: TestClient):
        resp = client.get("/health")
        assert "strict-origin" in resp.headers.get("Referrer-Policy", "")

    def test_permissions_policy(self, client: TestClient):
        resp = client.get("/health")
        assert "camera=()" in resp.headers.get("Permissions-Policy", "")


class TestRateLimiterCleanup:
    def test_stale_keys_are_pruned(self):
        """Rate limiter should clean up stale IP entries to prevent memory leak."""
        from src.interfaces.middleware import _RateLimitBucket

        bucket = _RateLimitBucket(max_requests=100, window_seconds=0)
        # Fill with many unique keys — all will be immediately stale (window=0)
        for i in range(10_002):
            bucket.is_allowed(f"ip-{i}")
        # After exceeding 10k keys, stale entries should be cleaned up
        # The last key stays, but stale ones are removed
        assert len(bucket._requests) < 10_000

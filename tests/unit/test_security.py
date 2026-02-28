"""Tests for the security module — permissions, audit, webhook verification."""

from __future__ import annotations

import time

import pytest

from src.models.schemas import Chunk, ChunkMetadata, SourceType
from src.security.auth import (
    AuditLogger,
    PermissionFilter,
    verify_github_signature,
    verify_slack_signature,
)


def _make_chunk(permissions: list[str] | None = None) -> Chunk:
    return Chunk(
        id="c1",
        content="secret stuff",
        metadata=ChunkMetadata(
            source_type=SourceType.PR_DESCRIPTION,
            source_id="PR-1",
            permissions=permissions or [],
        ),
    )


class TestPermissionFilter:
    def test_no_restrictions_passes_all(self):
        f = PermissionFilter()
        chunks = [_make_chunk(["repo:backend"]), _make_chunk(["repo:frontend"])]
        assert len(f.filter(chunks, set())) == 2

    def test_filters_by_permission(self):
        f = PermissionFilter()
        chunks = [_make_chunk(["repo:backend"]), _make_chunk(["repo:frontend"])]
        result = f.filter(chunks, {"repo:backend"})
        assert len(result) == 1
        assert result[0].metadata.permissions == ["repo:backend"]

    def test_chunk_without_permissions_is_allowed(self):
        f = PermissionFilter()
        chunks = [_make_chunk()]  # no permissions set
        result = f.filter(chunks, {"repo:backend"})
        assert len(result) == 1

    def test_mixed_permissions(self):
        f = PermissionFilter()
        chunks = [
            _make_chunk(["repo:backend"]),
            _make_chunk(["repo:frontend"]),
            _make_chunk(),  # no restrictions
        ]
        result = f.filter(chunks, {"repo:backend"})
        assert len(result) == 2  # backend + unrestricted


class TestAuditLogger:
    def test_log_creates_entry(self):
        logger = AuditLogger()
        entry = logger.log(user_id="u1", query="why?")
        assert entry.user_id == "u1"
        assert entry.query == "why?"
        assert len(logger.entries) == 1

    def test_multiple_logs(self):
        logger = AuditLogger()
        logger.log(user_id="u1", query="q1")
        logger.log(user_id="u2", query="q2")
        assert len(logger.entries) == 2

    def test_empty_user_id_raises(self):
        logger = AuditLogger()
        with pytest.raises(ValueError):
            logger.log(user_id="", query="q1")

    def test_clear(self):
        logger = AuditLogger()
        logger.log(user_id="u1", query="q1")
        logger.clear()
        assert len(logger.entries) == 0

    def test_entries_returns_copy(self):
        logger = AuditLogger()
        logger.log(user_id="u1", query="q1")
        entries = logger.entries
        entries.clear()
        assert len(logger.entries) == 1


class TestGitHubWebhookVerification:
    def test_valid_signature(self):
        import hashlib
        import hmac

        secret = "test-secret"
        payload = b'{"action": "opened"}'
        sig = "sha256=" + hmac.new(
            secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        assert verify_github_signature(payload, sig, secret) is True

    def test_invalid_signature(self):
        assert verify_github_signature(b"payload", "sha256=wrong", "secret") is False

    def test_missing_prefix(self):
        assert verify_github_signature(b"payload", "wrong", "secret") is False

    def test_empty_secret(self):
        assert verify_github_signature(b"payload", "sha256=abc", "") is False

    def test_empty_signature(self):
        assert verify_github_signature(b"payload", "", "secret") is False


class TestSlackSignatureVerification:
    def test_valid_signature(self):
        import hashlib
        import hmac

        secret = "slack-secret"
        timestamp = str(int(time.time()))
        payload = b'{"text": "hello"}'
        base = f"v0:{timestamp}:{payload.decode()}"
        expected = hmac.new(secret.encode(), base.encode(), hashlib.sha256).hexdigest()
        sig = f"v0={expected}"
        assert verify_slack_signature(payload, timestamp, sig, secret) is True

    def test_old_timestamp_rejected(self):
        """Requests older than 5 minutes should be rejected (replay protection)."""
        import hashlib
        import hmac

        secret = "slack-secret"
        timestamp = str(int(time.time()) - 600)  # 10 minutes ago
        payload = b'{"text": "hello"}'
        base = f"v0:{timestamp}:{payload.decode()}"
        expected = hmac.new(secret.encode(), base.encode(), hashlib.sha256).hexdigest()
        sig = f"v0={expected}"
        assert verify_slack_signature(payload, timestamp, sig, secret) is False

    def test_empty_params_rejected(self):
        assert verify_slack_signature(b"x", "", "sig", "secret") is False
        assert verify_slack_signature(b"x", "123", "", "secret") is False
        assert verify_slack_signature(b"x", "123", "sig", "") is False

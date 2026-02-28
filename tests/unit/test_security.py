"""Tests for the security module — permissions, audit, webhook verification."""

from __future__ import annotations

from src.models.schemas import Chunk, ChunkMetadata, SourceType
from src.security.auth import (
    AuditLogger,
    PermissionFilter,
    verify_github_signature,
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


class TestWebhookVerification:
    def test_valid_github_signature(self):
        import hashlib
        import hmac

        secret = "test-secret"
        payload = b'{"action": "opened"}'
        sig = "sha256=" + hmac.new(
            secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        assert verify_github_signature(payload, sig, secret) is True

    def test_invalid_github_signature(self):
        assert verify_github_signature(b"payload", "sha256=wrong", "secret") is False

    def test_missing_prefix(self):
        assert verify_github_signature(b"payload", "wrong", "secret") is False

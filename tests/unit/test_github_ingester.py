"""Tests for the GitHub ingester helpers (parsing, not HTTP calls)."""

from __future__ import annotations

from src.ingestion.github_ingester import GitHubIngester, _extract_linked_issues


class TestExtractLinkedIssues:
    def test_github_style_refs(self):
        body = "Fixes #123 and relates to #456"
        refs = _extract_linked_issues(body)
        assert "123" in refs
        assert "456" in refs

    def test_jira_style_refs(self):
        body = "Implements ENG-100 and resolves DATA-42"
        refs = _extract_linked_issues(body)
        assert "ENG-100" in refs
        assert "DATA-42" in refs

    def test_no_refs(self):
        assert _extract_linked_issues("No references here") == []


class TestParseWebhookPR:
    def test_valid_payload(self):
        payload = {
            "action": "opened",
            "pull_request": {
                "number": 42,
                "title": "Add auth",
                "body": "Fixes #10 and ENG-50",
                "user": {"login": "alice"},
                "merged_by": None,
                "created_at": "2024-01-15T10:00:00Z",
            },
            "repository": {"full_name": "acme/backend"},
        }
        pr = GitHubIngester.parse_webhook_pr(payload)
        assert pr is not None
        assert pr.pr_id == "42"
        assert pr.title == "Add auth"
        assert pr.repo == "acme/backend"
        assert "10" in pr.linked_issues
        assert "ENG-50" in pr.linked_issues

    def test_missing_pr_key(self):
        assert GitHubIngester.parse_webhook_pr({"action": "opened"}) is None

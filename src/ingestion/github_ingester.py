"""GitHub ingestion — pulls PRs, commits, and repo metadata via the REST API."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from src.models.schemas import CommitData, PRData

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"


class GitHubIngester:
    """Fetches and normalises data from GitHub repositories."""

    def __init__(self, token: str) -> None:
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    async def ingest_repository(self, owner: str, repo: str) -> dict[str, Any]:
        """Return normalised PRs and commits for a repository."""
        prs = await self.fetch_pull_requests(owner, repo)
        commits = await self.fetch_commits(owner, repo)
        return {"pull_requests": prs, "commits": commits}

    # ------------------------------------------------------------------
    # Pull requests
    # ------------------------------------------------------------------

    async def fetch_pull_requests(
        self,
        owner: str,
        repo: str,
        *,
        state: str = "all",
        per_page: int = 30,
        page: int = 1,
    ) -> list[PRData]:
        """Fetch pull requests for *owner/repo*."""
        url = f"{_GITHUB_API}/repos/{owner}/{repo}/pulls"
        params: dict[str, Any] = {
            "state": state,
            "per_page": per_page,
            "page": page,
            "sort": "updated",
            "direction": "desc",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self._headers, params=params, timeout=30)
            resp.raise_for_status()
            raw_prs: list[dict[str, Any]] = resp.json()

        results: list[PRData] = []
        for pr in raw_prs:
            comments = await self._fetch_pr_comments(owner, repo, pr["number"])
            results.append(
                PRData(
                    pr_id=str(pr["number"]),
                    repo=f"{owner}/{repo}",
                    title=pr.get("title", ""),
                    description=pr.get("body") or "",
                    author=pr.get("user", {}).get("login", ""),
                    merged_by=(pr.get("merged_by") or {}).get("login", ""),
                    comments=comments,
                    linked_issues=_extract_linked_issues(pr.get("body") or ""),
                    timestamp=_parse_ts(pr.get("created_at")),
                )
            )
        return results

    # ------------------------------------------------------------------
    # Commits
    # ------------------------------------------------------------------

    async def fetch_commits(
        self,
        owner: str,
        repo: str,
        *,
        per_page: int = 30,
        page: int = 1,
    ) -> list[CommitData]:
        """Fetch recent commits for *owner/repo*."""
        url = f"{_GITHUB_API}/repos/{owner}/{repo}/commits"
        params: dict[str, Any] = {"per_page": per_page, "page": page}
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self._headers, params=params, timeout=30)
            resp.raise_for_status()
            raw: list[dict[str, Any]] = resp.json()

        return [
            CommitData(
                sha=c["sha"],
                repo=f"{owner}/{repo}",
                message=c.get("commit", {}).get("message", ""),
                author=c.get("commit", {}).get("author", {}).get("name", ""),
                timestamp=_parse_ts(c.get("commit", {}).get("author", {}).get("date")),
            )
            for c in raw
        ]

    # ------------------------------------------------------------------
    # Webhook payload handling
    # ------------------------------------------------------------------

    @staticmethod
    def parse_webhook_pr(payload: dict[str, Any]) -> PRData | None:
        """Parse a ``pull_request`` webhook event into a *PRData*."""
        pr = payload.get("pull_request")
        if pr is None:
            return None
        return PRData(
            pr_id=str(pr["number"]),
            repo=payload.get("repository", {}).get("full_name", ""),
            title=pr.get("title", ""),
            description=pr.get("body") or "",
            author=pr.get("user", {}).get("login", ""),
            merged_by=(pr.get("merged_by") or {}).get("login", ""),
            linked_issues=_extract_linked_issues(pr.get("body") or ""),
            timestamp=_parse_ts(pr.get("created_at")),
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _fetch_pr_comments(
        self, owner: str, repo: str, pr_number: int
    ) -> list[str]:
        """Fetch review comments for a single PR."""
        url = f"{_GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/comments"
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url, headers=self._headers, params={"per_page": 50}, timeout=30,
            )
            if resp.status_code != 200:
                logger.warning("Failed to fetch PR comments for %s/%s#%s", owner, repo, pr_number)
                return []
            return [c.get("body", "") for c in resp.json()]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _extract_linked_issues(body: str) -> list[str]:
    """Extract issue references like ``#123`` or ``ENG-456`` from text."""
    import re

    refs: list[str] = []
    # GitHub-style #123
    refs.extend(re.findall(r"#(\d+)", body))
    # Jira/Linear-style ABC-123
    refs.extend(re.findall(r"[A-Z]{2,10}-\d+", body))
    return refs

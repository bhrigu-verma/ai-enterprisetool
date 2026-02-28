"""Entity linker — resolves references between PRs, tickets, and Slack threads.

Uses a combination of exact-match ID extraction and fuzzy text matching to
link related artefacts across data sources so that context assembly can
follow the decision chain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher


@dataclass(frozen=True)
class EntityRef:
    """A reference to an engineering artefact."""

    kind: str   # "pr", "ticket", "slack_thread", "commit"
    id: str     # "42", "ENG-100", "C123:1234.5678", "abc123"

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.id}"


@dataclass
class LinkedEntity:
    """An artefact with its resolved links to other artefacts."""

    ref: EntityRef
    title: str = ""
    links: list[EntityRef] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_GITHUB_PR_RE = re.compile(r"(?:^|\s)#(\d+)\b")
_JIRA_RE = re.compile(r"\b([A-Z]{2,10}-\d+)\b")
_COMMIT_SHA_RE = re.compile(r"\b([0-9a-f]{7,40})\b")
_SLACK_LINK_RE = re.compile(r"<#(C[A-Z0-9]+)\|")


class EntityLinker:
    """Extracts and links entity references across text sources."""

    def __init__(self, *, fuzzy_threshold: float = 0.3) -> None:
        self._fuzzy_threshold = fuzzy_threshold
        self._known_entities: dict[str, LinkedEntity] = {}

    # ------------------------------------------------------------------
    # Registration — build the entity index
    # ------------------------------------------------------------------

    def register(self, ref: EntityRef, title: str = "") -> None:
        """Register a known entity so it can be matched later."""
        self._known_entities[ref.key] = LinkedEntity(ref=ref, title=title)

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    def extract_refs(self, text: str) -> list[EntityRef]:
        """Extract all entity references from free-form text."""
        refs: list[EntityRef] = []

        for m in _GITHUB_PR_RE.finditer(text):
            refs.append(EntityRef(kind="pr", id=m.group(1)))

        for m in _JIRA_RE.finditer(text):
            refs.append(EntityRef(kind="ticket", id=m.group(1)))

        for m in _COMMIT_SHA_RE.finditer(text):
            if len(m.group(1)) >= 7:
                refs.append(EntityRef(kind="commit", id=m.group(1)))

        for m in _SLACK_LINK_RE.finditer(text):
            refs.append(EntityRef(kind="slack_channel", id=m.group(1)))

        return refs

    # ------------------------------------------------------------------
    # Linking
    # ------------------------------------------------------------------

    def link(self, source_ref: EntityRef, text: str) -> list[EntityRef]:
        """Find entities referenced in *text* and create bidirectional links.

        Returns the list of newly linked entity refs.
        """
        found = self.extract_refs(text)
        linked: list[EntityRef] = []

        for ref in found:
            if ref.key == source_ref.key:
                continue  # don't self-link

            # Register source if not known
            if source_ref.key not in self._known_entities:
                self._known_entities[source_ref.key] = LinkedEntity(ref=source_ref)

            src_entity = self._known_entities[source_ref.key]

            # Add forward link
            if ref not in src_entity.links:
                src_entity.links.append(ref)

            # Add reverse link if target is known
            if ref.key in self._known_entities:
                target = self._known_entities[ref.key]
                if source_ref not in target.links:
                    target.links.append(source_ref)

            linked.append(ref)
        return linked

    # ------------------------------------------------------------------
    # Fuzzy matching
    # ------------------------------------------------------------------

    def fuzzy_match_title(self, query: str) -> list[LinkedEntity]:
        """Find entities whose title fuzzy-matches the query.

        Uses a combination of SequenceMatcher and token-overlap scoring
        to handle reordered words (e.g. "auth refactor" ↔ "Refactor auth middleware").
        """
        query_lower = query.lower()
        query_tokens = set(query_lower.split())
        matches: list[tuple[float, LinkedEntity]] = []
        for entity in self._known_entities.values():
            if not entity.title:
                continue
            title_lower = entity.title.lower()
            title_tokens = set(title_lower.split())

            # Sequence similarity
            seq_ratio = SequenceMatcher(None, query_lower, title_lower).ratio()

            # Token overlap (Jaccard-like)
            overlap = len(query_tokens & title_tokens)
            union = len(query_tokens | title_tokens)
            token_ratio = overlap / union if union else 0.0

            # Combined score — weighted towards token overlap
            score = 0.4 * seq_ratio + 0.6 * token_ratio

            if score >= self._fuzzy_threshold:
                matches.append((score, entity))
        matches.sort(key=lambda x: x[0], reverse=True)
        return [m[1] for m in matches]

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_links(self, ref: EntityRef) -> list[EntityRef]:
        """Return all entities linked to *ref*."""
        entity = self._known_entities.get(ref.key)
        return list(entity.links) if entity else []

    @property
    def entity_count(self) -> int:
        return len(self._known_entities)

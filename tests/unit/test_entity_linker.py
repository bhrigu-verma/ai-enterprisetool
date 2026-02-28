"""Tests for the entity linker."""

from __future__ import annotations

from src.processing.entity_linker import EntityLinker, EntityRef


class TestEntityRefExtraction:
    def test_extract_github_pr_refs(self):
        linker = EntityLinker()
        refs = linker.extract_refs("Fixed in #42 and #100")
        ids = {r.id for r in refs if r.kind == "pr"}
        assert "42" in ids
        assert "100" in ids

    def test_extract_jira_refs(self):
        linker = EntityLinker()
        refs = linker.extract_refs("Implements ENG-200 and DATA-42")
        ids = {r.id for r in refs if r.kind == "ticket"}
        assert "ENG-200" in ids
        assert "DATA-42" in ids

    def test_extract_commit_sha(self):
        linker = EntityLinker()
        refs = linker.extract_refs("See commit abc1234 for details")
        assert any(r.kind == "commit" and r.id == "abc1234" for r in refs)

    def test_no_refs(self):
        linker = EntityLinker()
        refs = linker.extract_refs("No references here")
        # Should only find things that look like hex strings of 7+ chars
        pr_refs = [r for r in refs if r.kind in ("pr", "ticket")]
        assert pr_refs == []


class TestEntityLinking:
    def test_link_creates_bidirectional_links(self):
        linker = EntityLinker()
        pr_ref = EntityRef(kind="pr", id="42")
        linker.register(pr_ref, title="Add auth middleware")

        ticket_ref = EntityRef(kind="ticket", id="ENG-100")
        linker.register(ticket_ref, title="Auth migration")

        # Link via text
        linked = linker.link(pr_ref, "Closes ENG-100")
        assert any(r.id == "ENG-100" for r in linked)

        # Reverse link should also exist
        reverse_links = linker.get_links(ticket_ref)
        assert any(r.id == "42" for r in reverse_links)

    def test_no_self_link(self):
        linker = EntityLinker()
        pr_ref = EntityRef(kind="pr", id="42")
        linker.register(pr_ref, title="Fix #42")
        linked = linker.link(pr_ref, "See #42 for context")
        # Should not self-link
        assert all(r.key != pr_ref.key for r in linked)


class TestFuzzyMatching:
    def test_fuzzy_match_finds_similar_titles(self):
        linker = EntityLinker()
        linker.register(EntityRef(kind="pr", id="1"), title="Refactor auth middleware")
        linker.register(EntityRef(kind="pr", id="2"), title="Add payments endpoint")

        matches = linker.fuzzy_match_title("the auth refactor")
        assert len(matches) >= 1
        assert matches[0].ref.id == "1"

    def test_fuzzy_match_no_results(self):
        linker = EntityLinker()
        linker.register(EntityRef(kind="pr", id="1"), title="Refactor auth")
        matches = linker.fuzzy_match_title("completely unrelated topic xyz")
        assert matches == []

    def test_entity_count(self):
        linker = EntityLinker()
        linker.register(EntityRef(kind="pr", id="1"))
        linker.register(EntityRef(kind="ticket", id="ENG-1"))
        assert linker.entity_count == 2

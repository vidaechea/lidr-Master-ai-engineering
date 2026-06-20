"""Unit tests for MetadataExtractor.

Coverage:
  - project name extraction from various transcript patterns
  - technology detection (known and unknown keywords)
  - team size extraction from LLM-response patterns
  - scope truncation at sentence boundary
  - incremental update (existing values are preserved)
  - graceful degradation when no signals are found
"""
from __future__ import annotations

import pytest

from app.generation.conversation.metadata_extractor import MetadataExtractor
from app.generation.conversation.sessions import ProjectMetadata


@pytest.fixture
def extractor() -> MetadataExtractor:
    return MetadataExtractor()


@pytest.fixture
def empty_meta() -> ProjectMetadata:
    return ProjectMetadata()


# ---------------------------------------------------------------------------
# _extract_project_name
# ---------------------------------------------------------------------------


class TestExtractProjectName:
    def test_named_pattern(self, extractor, empty_meta):
        meta = extractor.update(
            "We are building an app called ShopEasy for our client.",
            "",
            empty_meta,
        )
        assert meta.project_name == "ShopEasy"

    def test_named_with_quotes(self, extractor, empty_meta):
        meta = extractor.update(
            'The project named "DataPipeline Pro" will process logs.',
            "",
            empty_meta,
        )
        assert meta.project_name == "DataPipeline Pro"

    def test_markdown_heading(self, extractor, empty_meta):
        meta = extractor.update(
            "# Invoice Tracker\n\nWe need a system to manage invoices.",
            "",
            empty_meta,
        )
        assert meta.project_name == "Invoice Tracker"

    def test_no_name_returns_none(self, extractor, empty_meta):
        meta = extractor.update(
            "We need some software to manage our inventory.",
            "",
            empty_meta,
        )
        assert meta.project_name is None

    def test_existing_name_is_not_overwritten(self, extractor):
        existing = ProjectMetadata(project_name="OldName")
        meta = extractor.update(
            "Building a new project called NewName.",
            "",
            existing,
        )
        assert meta.project_name == "OldName"


# ---------------------------------------------------------------------------
# _extract_technologies
# ---------------------------------------------------------------------------


class TestExtractTechnologies:
    def test_detects_known_frontend_tech(self, extractor, empty_meta):
        meta = extractor.update("We will use React and TypeScript.", "", empty_meta)
        assert "react" in meta.mentioned_technologies
        assert "typescript" in meta.mentioned_technologies

    def test_detects_backend_and_database(self, extractor, empty_meta):
        meta = extractor.update(
            "Backend in FastAPI with PostgreSQL and Redis cache.", "", empty_meta
        )
        assert "fastapi" in meta.mentioned_technologies
        assert "postgresql" in meta.mentioned_technologies
        assert "redis" in meta.mentioned_technologies

    def test_unknown_tech_not_added(self, extractor, empty_meta):
        meta = extractor.update("We use our custom XyzFramework.", "", empty_meta)
        assert "xyzframework" not in meta.mentioned_technologies

    def test_case_insensitive_detection(self, extractor, empty_meta):
        meta = extractor.update("Backend with FASTAPI and REACT frontend.", "", empty_meta)
        assert "fastapi" in meta.mentioned_technologies
        assert "react" in meta.mentioned_technologies

    def test_accumulates_across_turns(self, extractor):
        first = extractor.update("Using React.", "", ProjectMetadata())
        second = extractor.update("And also FastAPI for the backend.", "", first)
        assert "react" in second.mentioned_technologies
        assert "fastapi" in second.mentioned_technologies

    def test_no_duplicates_across_turns(self, extractor):
        first = extractor.update("Using React.", "", ProjectMetadata())
        second = extractor.update("Also using React on the frontend.", "", first)
        assert second.mentioned_technologies.count("react") == 1

    def test_technologies_are_sorted(self, extractor, empty_meta):
        meta = extractor.update("Stack: Redis, Angular, Docker.", "", empty_meta)
        assert meta.mentioned_technologies == sorted(meta.mentioned_technologies)

    def test_scans_llm_response_too(self, extractor, empty_meta):
        meta = extractor.update(
            "Build a platform.",
            "I recommend using Kubernetes for deployment.",
            empty_meta,
        )
        assert "kubernetes" in meta.mentioned_technologies


# ---------------------------------------------------------------------------
# _extract_team_size
# ---------------------------------------------------------------------------


class TestExtractTeamSize:
    def test_team_of_n_pattern(self, extractor, empty_meta):
        meta = extractor.update("", "Estimated for a team of 4.", empty_meta)
        assert meta.assumed_team_size == 4

    def test_n_developers_pattern(self, extractor, empty_meta):
        meta = extractor.update("", "This requires 3 developers full-time.", empty_meta)
        assert meta.assumed_team_size == 3

    def test_n_person_team_pattern(self, extractor, empty_meta):
        meta = extractor.update("", "Suited for a 5-person team.", empty_meta)
        assert meta.assumed_team_size == 5

    def test_no_team_size_returns_none(self, extractor, empty_meta):
        meta = extractor.update("", "No team information available.", empty_meta)
        assert meta.assumed_team_size is None

    def test_existing_team_size_is_not_overwritten(self, extractor):
        existing = ProjectMetadata(assumed_team_size=3)
        meta = extractor.update("", "This needs a team of 7.", existing)
        assert meta.assumed_team_size == 3

    def test_out_of_bounds_size_ignored(self, extractor, empty_meta):
        meta = extractor.update("", "We have 99 developers for this.", empty_meta)
        assert meta.assumed_team_size is None


# ---------------------------------------------------------------------------
# _extract_scope
# ---------------------------------------------------------------------------


class TestExtractScope:
    def test_short_transcript_stored_as_is(self, extractor, empty_meta):
        transcript = "Build a small invoicing tool."
        meta = extractor.update(transcript, "", empty_meta)
        assert meta.agreed_scope == transcript

    def test_long_transcript_truncated_at_sentence_boundary(self, extractor, empty_meta):
        sentence = "This is a sentence. "
        transcript = sentence * 20  # 400 chars
        meta = extractor.update(transcript, "", empty_meta)
        assert meta.agreed_scope is not None
        assert len(meta.agreed_scope) <= 320
        assert meta.agreed_scope.endswith(".")

    def test_empty_transcript_returns_none_scope(self, extractor, empty_meta):
        meta = extractor.update("", "", empty_meta)
        assert meta.agreed_scope is None

    def test_existing_scope_not_overwritten(self, extractor):
        existing = ProjectMetadata(agreed_scope="original scope")
        meta = extractor.update("new transcript content here.", "", existing)
        assert meta.agreed_scope == "original scope"


# ---------------------------------------------------------------------------
# Full update / incremental enrichment
# ---------------------------------------------------------------------------


class TestIncrementalUpdate:
    def test_first_call_empty_metadata(self, extractor, empty_meta):
        meta = extractor.update("Describe a project.", "", empty_meta)
        assert isinstance(meta, ProjectMetadata)

    def test_successive_calls_accumulate_technologies(self, extractor):
        meta = ProjectMetadata()
        meta = extractor.update("We use React.", "", meta)
        meta = extractor.update("Backend is FastAPI.", "", meta)
        meta = extractor.update("Database is PostgreSQL.", "", meta)
        assert "react" in meta.mentioned_technologies
        assert "fastapi" in meta.mentioned_technologies
        assert "postgresql" in meta.mentioned_technologies

    def test_update_returns_new_instance(self, extractor, empty_meta):
        result = extractor.update("Some project.", "", empty_meta)
        assert result is not empty_meta


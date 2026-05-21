"""Golden dataset for LLM evaluation tests (Families 2 and 3).

Each GoldenCase represents a curated input with expected behaviour metadata.
The dataset covers the full spectrum of real inputs: simple, medium, large,
ambiguous, and contradictory scope.

Usage
-----
Import GOLDEN_CASES for parametrized tests, and run_estimate / run_estimate_sync
to call the real estimation service in evaluation tests.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TypedDict

from app.schemas.estimation import EstimationRequest, EstimationResponse
from app.services.estimation_service import EstimationService

_FIXTURES = Path(__file__).parent.parent.parent / "app" / "fixtures"


# ---------------------------------------------------------------------------
# Dataset schema
# ---------------------------------------------------------------------------


class GoldenCase(TypedDict):
    id: str
    category: str
    transcript: str
    expected_hours_min: int
    expected_hours_max: int
    expected_components: list[str]
    key_risks: list[str]


# ---------------------------------------------------------------------------
# Golden cases
# ---------------------------------------------------------------------------

GOLDEN_CASES: list[GoldenCase] = [
    GoldenCase(
        id="small_landing_page",
        category="small_project",
        transcript=(
            "Build a simple landing page with a contact form, newsletter subscription, "
            "and basic Google Analytics integration. One-page static site, "
            "mobile-responsive. Deploy to Vercel. No backend needed beyond the form."
        ),
        expected_hours_min=16,
        expected_hours_max=120,
        expected_components=["frontend", "form_handling"],
        key_risks=["scope creep on design", "third-party integration latency"],
    ),
    GoldenCase(
        id="medium_admin_portal",
        category="medium_project",
        transcript=(_FIXTURES / "short_transcription.txt").read_text(encoding="utf-8"),
        expected_hours_min=160,
        expected_hours_max=400,
        expected_components=["backend", "frontend", "auth", "rbac", "audit_log"],
        key_risks=["SSO integration complexity", "RBAC design", "audit log performance"],
    ),
    GoldenCase(
        id="large_reservation_system",
        category="large_project",
        transcript=(
            "A restaurant chain with 15 locations needs a unified reservation platform. "
            "Custom build — no white-label SaaS. "
            "Features: online booking via web (mobile-responsive), floor management for hosts, "
            "customer profiles with loyalty points that stack across all restaurants, "
            "integration with an existing Java/Spring Boot loyalty backend (REST/OAuth2), "
            "integration with the BCN-Touch POS system (self-hosted REST API per restaurant, "
            "connected via VPN), dynamic table suggestions for regulars, dormant customer alerts "
            "for managers, multi-role access (customers, restaurant managers, HQ analytics, "
            "regional managers), reporting dashboard across all locations. "
            "No chatbot. Phase 1: core reservation + loyalty + POS integration. "
            "Phase 2: AI-driven suggestions and menu promotion."
        ),
        expected_hours_min=600,
        expected_hours_max=2000,
        expected_components=[
            "backend",
            "frontend",
            "loyalty_integration",
            "pos_integration",
            "auth",
            "analytics",
        ],
        key_risks=[
            "POS API quality",
            "loyalty system integration",
            "multi-location data model",
            "cold-start recommender",
        ],
    ),
    GoldenCase(
        id="ambiguous_internal_tool",
        category="ambiguous",
        transcript=(
            "We need something to manage our internal processes better. "
            "Something with dashboards and reports. Should integrate with what we already have."
        ),
        # Wide range: ambiguity makes any estimate defensible
        expected_hours_min=40,
        expected_hours_max=800,
        expected_components=[],
        key_risks=["undefined scope", "integration unknowns"],
    ),
    GoldenCase(
        id="contradictory_scope",
        category="edge_case",
        transcript=(
            "Build a simple MVP. Just a basic CRUD app. "
            "Requirements: real-time collaboration like Google Docs, AI-powered content generation, "
            "multi-tenant SaaS with per-tenant billing, mobile apps for iOS and Android, "
            "offline mode with sync conflict resolution, GDPR compliance with right-to-erasure, "
            "SSO with 10+ identity providers, audit logging, custom reporting engine, "
            "and a documented public API. Timeline: 2 weeks. Budget: minimal."
        ),
        expected_hours_min=400,
        expected_hours_max=3000,
        expected_components=["backend", "frontend", "mobile", "auth", "billing", "api"],
        key_risks=["scope vs timeline mismatch", "technical debt", "feature prioritization"],
    ),
]


# ---------------------------------------------------------------------------
# Service helpers
# ---------------------------------------------------------------------------


def _build_request(transcript: str) -> EstimationRequest:
    """Build a minimal EstimationRequest for eval runs (low token usage)."""
    return EstimationRequest(
        transcription=transcript,
        evaluate=True,
        num_examples=1,
        max_output_tokens=1024,
    )


async def run_estimate(transcript: str) -> EstimationResponse:
    """Call the real EstimationService. Requires valid LLM API keys in the environment."""
    service = EstimationService()
    return await service.estimate(_build_request(transcript))


def run_estimate_sync(transcript: str) -> EstimationResponse:
    """Synchronous wrapper around run_estimate for use in non-async test functions."""
    return asyncio.run(run_estimate(transcript))


# ---------------------------------------------------------------------------
# Hours extraction helper (shared by both eval test files)
# ---------------------------------------------------------------------------


def extract_total_hours(response: EstimationResponse) -> int | None:
    """Extract total hours from an EstimationResponse.

    Tries in order:
    1. validation.declared_total_hours  (parsed from '**Total hours:** N' in markdown)
    2. validation.sum_row_hours         (sum of table rows)

    Returns None when the markdown is too malformed to parse hours — which is
    itself a hard-determinism failure captured by test_output_validator tests.
    """
    if response.validation is None:
        return None
    if response.validation.declared_total_hours is not None:
        return response.validation.declared_total_hours
    return response.validation.sum_row_hours

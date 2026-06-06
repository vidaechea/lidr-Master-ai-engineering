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

from app.domain.schemas.estimation import EstimationRequest, EstimationResponse
from app.domain.estimation_service import EstimationService

_FIXTURES = Path(__file__).parent.parent.parent / "app" / "foundation" / "fixtures"


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
    GoldenCase(
        id="small_todo_app",
        category="small_project",
        transcript=(
            "Create a simple to-do list web application. Users can add, edit, mark as complete, "
            "and delete tasks. Store data in browser localStorage. Mobile responsive design. "
            "No backend needed. Deploy to GitHub Pages."
        ),
        expected_hours_min=8,
        expected_hours_max=40,
        expected_components=["frontend", "storage"],
        key_risks=["localStorage limitations", "offline sync"],
    ),
    GoldenCase(
        id="small_calculator_widget",
        category="small_project",
        transcript=(
            "Build a scientific calculator web widget. Support basic math operations, "
            "trigonometric functions, and unit conversions. Responsive design. "
            "Can be embedded as an iframe or standalone."
        ),
        expected_hours_min=16,
        expected_hours_max=60,
        expected_components=["frontend", "ui"],
        key_risks=["calculation accuracy", "floating point precision"],
    ),
    GoldenCase(
        id="small_blog_system",
        category="small_project",
        transcript=(
            "Simple blog platform for a single author. Features: markdown post editor, "
            "post listing with pagination, search by title/tags, RSS feed generation. "
            "Static site generation with Next.js. Comments disabled initially. "
            "Hosting on Vercel."
        ),
        expected_hours_min=20,
        expected_hours_max=80,
        expected_components=["frontend", "ssg", "content"],
        key_risks=["SEO optimization", "performance tuning"],
    ),
    GoldenCase(
        id="small_expense_tracker",
        category="small_project",
        transcript=(
            "Personal expense tracker app. Add expenses with category, date, and amount. "
            "Monthly reports with pie charts. Export to CSV. Data persisted in local database. "
            "Single user, no authentication needed."
        ),
        expected_hours_min=24,
        expected_hours_max=100,
        expected_components=["frontend", "charts", "export"],
        key_risks=["data integrity", "export accuracy"],
    ),
    GoldenCase(
        id="medium_ecommerce_platform",
        category="medium_project",
        transcript=(
            "E-commerce platform for a small boutique. Features: product catalog with images, "
            "shopping cart, checkout with Stripe integration, order tracking, email notifications, "
            "inventory management, admin dashboard for products and orders. Single warehouse. "
            "No multi-vendor. Social login with Google and Facebook."
        ),
        expected_hours_min=200,
        expected_hours_max=500,
        expected_components=["backend", "frontend", "payment", "auth", "inventory"],
        key_risks=["payment gateway reliability", "inventory sync", "scalability"],
    ),
    GoldenCase(
        id="medium_crm_system",
        category="medium_project",
        transcript=(
            "Customer Relationship Management system for a sales team of 20 people. "
            "Track leads, opportunities, and customer interactions. Pipeline visualization. "
            "Email integration with Gmail. Task assignment and reminders. "
            "Reports on conversion rates and pipeline value. Role-based access control. "
            "Cloud-based deployment."
        ),
        expected_hours_min=180,
        expected_hours_max=450,
        expected_components=["backend", "frontend", "email_integration", "auth", "reporting"],
        key_risks=["email sync reliability", "data migration", "concurrent access"],
    ),
    GoldenCase(
        id="medium_learning_management_system",
        category="medium_project",
        transcript=(
            "Learning management system for an online education company. Features: course creation, "
            "video hosting and streaming, student enrollment, progress tracking, quiz and assessment system, "
            "certificates upon completion, student discussion forums, instructor dashboard with analytics. "
            "Supports up to 1000 concurrent users. Payment integration for course sales."
        ),
        expected_hours_min=220,
        expected_hours_max=550,
        expected_components=["backend", "frontend", "video_streaming", "payment", "analytics"],
        key_risks=["video infrastructure costs", "concurrent streaming", "forum moderation"],
    ),
    GoldenCase(
        id="medium_social_feed",
        category="medium_project",
        transcript=(
            "Social media feed platform. Users can post text and images, like, comment, and share. "
            "Real-time notifications for likes and comments. User profiles with follower/following. "
            "Full-text search on posts. Image optimization and CDN delivery. "
            "Moderation tools for admins. 10K daily active users expected."
        ),
        expected_hours_min=200,
        expected_hours_max=480,
        expected_components=["backend", "frontend", "real-time", "cdn", "search"],
        key_risks=["real-time message queue", "image storage", "database scalability"],
    ),
    GoldenCase(
        id="large_marketplace_platform",
        category="large_project",
        transcript=(
            "Multi-vendor marketplace platform similar to eBay. Vendors can list products with images, pricing, "
            "inventory. Buyers search, filter, and purchase. Payment processing with split between platform and vendors. "
            "Dispute resolution system. Vendor analytics dashboard. Customer reviews and ratings. "
            "Fraud detection for suspicious transactions. Mobile app for iOS and Android. "
            "Support for multiple currencies and countries. Partner integration APIs for vendors."
        ),
        expected_hours_min=800,
        expected_hours_max=2400,
        expected_components=[
            "backend",
            "frontend",
            "mobile",
            "payment",
            "fraud_detection",
            "analytics",
            "api",
        ],
        key_risks=[
            "payment processor reliability",
            "fraud patterns",
            "vendor management",
            "data security",
        ],
    ),
    GoldenCase(
        id="large_healthcare_system",
        category="large_project",
        transcript=(
            "Healthcare management system for a hospital network with 5 locations. "
            "Patient records system with HIPAA compliance. Appointment scheduling with doctor availability. "
            "Electronic prescriptions integrated with pharmacy systems. Lab results management. "
            "Billing and insurance claim processing. Staff portal with role-based access. "
            "Telemedicine capability for video consultations. Audit logging for compliance. "
            "Integration with existing EHR systems via HL7. Real-time bed management."
        ),
        expected_hours_min=1000,
        expected_hours_max=3000,
        expected_components=[
            "backend",
            "frontend",
            "telemedicine",
            "ehr_integration",
            "billing",
            "compliance",
        ],
        key_risks=[
            "HIPAA compliance",
            "data security",
            "legacy system integration",
            "concurrent load",
        ],
    ),
    GoldenCase(
        id="ambiguous_data_system",
        category="ambiguous",
        transcript=(
            "We need a system to handle our data. Something that can analyze and visualize it. "
            "Maybe real-time dashboards. Should work with what we have now and be ready for future growth."
        ),
        expected_hours_min=80,
        expected_hours_max=1200,
        expected_components=[],
        key_risks=["data source undefined", "analysis requirements unclear", "infrastructure unknowns"],
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



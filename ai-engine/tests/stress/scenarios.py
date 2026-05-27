"""Synthetic stress tests for multi-turn conversational estimation workflows.

This module defines three scenario profiles designed to test system behavior:

1. **ProjectGrowth**: Accumulate features incrementally (MVP → auth → multi-tenant → audit).
   Measures: cost curve, project_name survival at turn 20.

2. **ProjectPivot**: Stack change at turn 5 (React → Flutter).
   Measures: metadata update cleanness (does mentioned_technologies replace or accumulate?).

3. **ProjectContradiction**: Budget changes (€30k at turn 3 → €80k at turn 8).
   Measures: which budget value is preserved/promoted, contradiction handling.

Each scenario declares a FactTracker: per-turn assertions about what the system
should remember. Mismatches feed into MemoryDriftMetric for evaluation.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.services.sessions import ProjectMetadata

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums & Types
# ---------------------------------------------------------------------------


class ScenarioType(str, Enum):
    """Scenario profile types."""
    GROWTH = "growth"
    PIVOT = "pivot"
    CONTRADICTION = "contradiction"


# ---------------------------------------------------------------------------
# Fact Tracker
# ---------------------------------------------------------------------------


@dataclass
class Fact:
    """A single assertion about what the system should remember."""
    key: str
    value: Any
    turn_number: int
    description: str


@dataclass
class FactTracker:
    """Tracks assertions per turn and measures memory drift."""
    scenario_id: str
    profile: ScenarioType
    facts: list[Fact] = field(default_factory=list)

    def add_fact(self, key: str, value: Any, turn_number: int, description: str) -> None:
        """Add an assertion that should be satisfied after the given turn."""
        self.facts.append(Fact(key=key, value=value, turn_number=turn_number, description=description))

    def verify_facts(
        self, actual_metadata: dict[str, Any], turn_number: int
    ) -> tuple[list[Fact], list[Fact]]:
        """Verify facts up to turn_number. Return (satisfied, violated)."""
        facts_to_check = [f for f in self.facts if f.turn_number <= turn_number]
        satisfied = []
        violated = []

        for fact in facts_to_check:
            actual_value = actual_metadata.get(fact.key)
            if self._match(actual_value, fact.value):
                satisfied.append(fact)
            else:
                violated.append(fact)

        return satisfied, violated

    @staticmethod
    def _match(actual: Any, expected: Any) -> bool:
        """Check if actual matches expected (handles strings, lists, etc.)."""
        if isinstance(expected, list):
            # For lists, check containment (e.g., technologies must include all expected)
            if not isinstance(actual, list):
                return False
            return all(item in actual for item in expected)
        elif isinstance(expected, str):
            # For strings, check substring containment
            if not isinstance(actual, str):
                return False
            return expected.lower() in actual.lower()
        else:
            return actual == expected

    def memory_drift_ratio(self, turn_number: int) -> float:
        """Return the fraction of violated facts up to turn_number."""
        satisfied, violated = self.verify_facts({}, turn_number)
        total = len(satisfied) + len(violated)
        if total == 0:
            return 0.0
        return len(violated) / total


# ---------------------------------------------------------------------------
# Turn Data & Results
# ---------------------------------------------------------------------------


@dataclass
class TurnResult:
    """Result of a single turn estimation."""
    turn_number: int
    transcript: str
    response: str
    cost_usd: Decimal
    input_tokens: int
    output_tokens: int
    latency_ms: float

    # Extracted metadata after this turn
    project_name: str | None = None
    mentioned_technologies: list[str] = field(default_factory=list)
    assumed_team_size: int | None = None
    agreed_scope: str | None = None

    # Fact-tracker results
    satisfied_facts: list[Fact] = field(default_factory=list)
    violated_facts: list[Fact] = field(default_factory=list)

    @property
    def memory_drift(self) -> float:
        """Fraction of facts violated in this turn."""
        total = len(self.satisfied_facts) + len(self.violated_facts)
        if total == 0:
            return 0.0
        return len(self.violated_facts) / total


@dataclass
class ScenarioResult:
    """Aggregated results for a full scenario run."""
    scenario_id: str
    profile: ScenarioType
    turns: list[TurnResult] = field(default_factory=list)
    total_cost_usd: Decimal = Decimal(0)
    error: str | None = None

    def add_turn(self, result: TurnResult) -> None:
        """Append a turn result and update aggregates."""
        self.turns.append(result)
        self.total_cost_usd += result.cost_usd

    @property
    def cost_curve(self) -> list[Decimal]:
        """Cumulative cost per turn."""
        cumulative = Decimal(0)
        curve = []
        for turn in self.turns:
            cumulative += turn.cost_usd
            curve.append(cumulative)
        return curve

    @property
    def avg_memory_drift(self) -> float:
        """Average memory drift ratio across all turns."""
        if not self.turns:
            return 0.0
        return sum(t.memory_drift for t in self.turns) / len(self.turns)

    @property
    def final_project_name(self) -> str | None:
        """Project name from the last turn."""
        for turn in reversed(self.turns):
            if turn.project_name:
                return turn.project_name
        return None

    @property
    def final_technologies(self) -> list[str]:
        """Technologies from the last turn."""
        for turn in reversed(self.turns):
            if turn.mentioned_technologies:
                return turn.mentioned_technologies
        return []

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-friendly dict."""
        return {
            "scenario_id": self.scenario_id,
            "profile": self.profile.value,
            "total_cost_usd": float(self.total_cost_usd),
            "cost_curve": [float(c) for c in self.cost_curve],
            "turns": [
                {
                    "turn_number": t.turn_number,
                    "transcript": t.transcript,
                    "cost_usd": float(t.cost_usd),
                    "tokens": {"in": t.input_tokens, "out": t.output_tokens},
                    "latency_ms": t.latency_ms,
                    "project_name": t.project_name,
                    "technologies": t.mentioned_technologies,
                    "memory_drift": t.memory_drift,
                    "satisfied_facts": len(t.satisfied_facts),
                    "violated_facts": len(t.violated_facts),
                }
                for t in self.turns
            ],
            "summary": {
                "avg_memory_drift": self.avg_memory_drift,
                "final_project_name": self.final_project_name,
                "final_technologies": self.final_technologies,
                "error": self.error,
            },
        }


# ---------------------------------------------------------------------------
# Scenario Definitions
# ---------------------------------------------------------------------------


class ScenarioProfile:
    """Base class for scenario profiles."""

    id: str
    profile_type: ScenarioType
    description: str
    turns: list[str]  # Turn transcripts
    fact_tracker: FactTracker

    def __init__(self):
        self.fact_tracker = FactTracker(
            scenario_id=self.id,
            profile=self.profile_type,
        )

    def get_transcript_for_turn(self, turn_number: int) -> str | None:
        """Get the transcript for a specific turn. Override in subclasses if needed."""
        return None

    def get_attachments_for_turn(
        self, turn_number: int, attachment_size_kb: int = 0
    ) -> dict[str, bytes] | None:
        """Get attachments for a specific turn as {filename: bytes}.

        Args:
            turn_number: Which turn this is.
            attachment_size_kb: If > 0, generate dummy attachment of this size.

        Returns:
            Dict of filename -> file bytes, or None if no attachments.
        """
        # Default: no attachments unless subclass overrides
        if attachment_size_kb <= 0:
            return None

        # Generate a dummy attachment of the specified size
        try:
            from tests.stress.generators.pdf import generate_pdf
            pdf_bytes = generate_pdf(attachment_size_kb)
            filename = f"attachment_turn{turn_number}_{attachment_size_kb}kb.pdf"
            return {filename: pdf_bytes}
        except Exception as e:
            log.warning(f"Failed to generate dummy attachment for turn {turn_number}: {e}")
            return None


class ProjectGrowthScenario(ScenarioProfile):
    """Scenario: Coherent feature accumulation.

    Turn 1: MVP (landing page + contact form)
    Turn 3: Add authentication
    Turn 6: Add multi-tenant support
    Turn 10: Add audit log
    Turn 20: Add data export (CSV)

    Tests:
      - Cost curve increases monotonically
      - project_name survives to turn 20
      - mentioned_technologies accumulate coherently (no removal)
    """

    def __init__(self):
        self.id = "growth_01"
        self.profile_type = ScenarioType.GROWTH
        self.description = "Coherent incremental feature growth"

        # Define turns
        self.turns = {
            1: (
                "We're building a SaaS platform called TaskMaster. "
                "Phase 1 is a simple landing page with a contact form and email notifications. "
                "Stack: React, Node.js, PostgreSQL."
            ),
            3: (
                "Now we need to add user authentication and authorization. "
                "Users will have profiles and can log in with email/password. "
                "We're using JWT tokens."
            ),
            6: (
                "The platform needs to support multiple tenants. "
                "Each tenant has isolated data. "
                "We need to add tenant isolation logic to the database."
            ),
            10: (
                "We need a comprehensive audit log. "
                "Track all user actions, data changes, and access events. "
                "Logs must be tamper-proof and queryable."
            ),
            20: (
                "Finally, add CSV export functionality. "
                "Users can export their data, audit logs, and reports as CSV. "
                "Use a background job queue for large exports."
            ),
        }

        super().__init__()

        # Define facts
        self.fact_tracker.add_fact(
            "project_name", "TaskMaster", 1, "Project name should be TaskMaster from turn 1"
        )
        self.fact_tracker.add_fact(
            "mentioned_technologies", ["React", "Node.js", "PostgreSQL"], 1,
            "Initial stack should include React, Node.js, PostgreSQL"
        )
        self.fact_tracker.add_fact(
            "mentioned_technologies", ["JWT"], 3,
            "JWT tokens should be mentioned by turn 3"
        )
        self.fact_tracker.add_fact(
            "mentioned_technologies", ["audit"], 10,
            "Audit capability should be mentioned by turn 10"
        )
        self.fact_tracker.add_fact(
            "mentioned_technologies", ["CSV"], 20,
            "CSV export should be mentioned by turn 20"
        )

    def get_transcript_for_turn(self, turn_number: int) -> str | None:
        """Get the transcript for a specific turn, or None if not defined."""
        return self.turns.get(turn_number)


class ProjectPivotScenario(ScenarioProfile):
    """Scenario: Technology stack pivot.

    Turn 1-4: React + REST API
    Turn 5: PIVOT to Flutter (mobile app) instead of React
    Turn 6+: Consolidate (Flutter + REST API)

    Tests:
      - At turn 5, React is replaced (or accumulated?)
      - mentioned_technologies reflects the pivot cleanly
      - No ghost references to old stack in turn 20
    """

    def __init__(self):
        self.id = "pivot_01"
        self.profile_type = ScenarioType.PIVOT
        self.description = "Technology stack pivot (React → Flutter)"

        self.turns = {
            1: (
                "Building a mobile-first CRM application called SalesFlow. "
                "Initially planned as a React web app with REST API backend."
            ),
            3: (
                "We've got the REST API running on FastAPI with PostgreSQL. "
                "React frontend is partially built."
            ),
            5: (
                "Actually, we're pivoting to Flutter for better mobile reach. "
                "Forget the React web app; we'll build iOS and Android with Flutter instead. "
                "Keep the same REST API backend."
            ),
            10: (
                "Flutter app is well underway. The backend is stable. "
                "We're now adding push notifications and offline sync."
            ),
            20: (
                "SalesFlow is shipping iOS and Android apps via Flutter. "
                "The REST API is running smoothly on FastAPI."
            ),
        }

        super().__init__()

        # Define facts
        self.fact_tracker.add_fact(
            "project_name", "SalesFlow", 1, "Project name is SalesFlow"
        )
        self.fact_tracker.add_fact(
            "mentioned_technologies", ["React", "REST"], 3,
            "React and REST API mentioned in early turns"
        )
        self.fact_tracker.add_fact(
            "mentioned_technologies", ["Flutter"], 5,
            "Flutter should be mentioned at pivot turn 5"
        )
        # After pivot, React should not be mentioned (or at least Flutter should be primary)
        self.fact_tracker.add_fact(
            "mentioned_technologies", ["Flutter", "FastAPI"], 20,
            "Final stack should be Flutter + FastAPI"
        )

    def get_transcript_for_turn(self, turn_number: int) -> str | None:
        return self.turns.get(turn_number)


class ProjectContradictionScenario(ScenarioProfile):
    """Scenario: Contradictory information (budget conflict).

    Turn 3: "Budget is €30,000"
    Turn 8: "Actually, budget is €80,000"
    Turn 20: Which budget is remembered? Which is promoted to anchor?

    Tests:
      - Contradiction is detected and logged
      - One budget value is preserved (the latest? or the anchor?)
      - MemoryDriftMetric measures disagreement
    """

    def __init__(self):
        self.id = "contradiction_01"
        self.profile_type = ScenarioType.CONTRADICTION
        self.description = "Budget contradiction (€30k → €80k)"

        self.turns = {
            1: (
                "We're building an enterprise logistics platform called LogHub. "
                "Frontend, backend, database, integrations with 3PL providers."
            ),
            3: (
                "Initial budget estimate: €30,000. "
                "Team of 3 developers, 8-week timeline."
            ),
            5: (
                "Scope is expanding. We need real-time tracking, mobile app, and API. "
                "Still working with €30k budget assumption."
            ),
            8: (
                "Stakeholders just approved a larger budget. "
                "New budget is €80,000. This is a significant increase. "
                "We can now include advanced analytics and machine learning features."
            ),
            15: (
                "With the €80k budget, we're adding predictive analytics. "
                "Scope is much larger than initially planned."
            ),
            20: (
                "Project scope and cost are now aligned to the €80,000 budget. "
                "Deliverables are comprehensive."
            ),
        }

        super().__init__()

        # Define facts
        self.fact_tracker.add_fact(
            "project_name", "LogHub", 1, "Project name is LogHub"
        )
        self.fact_tracker.add_fact(
            "budget", "30000", 3, "Budget is €30,000 at turn 3"
        )
        self.fact_tracker.add_fact(
            "budget", "80000", 8, "Budget updated to €80,000 at turn 8"
        )
        # At turn 20, which budget is primary? Should be 80k
        self.fact_tracker.add_fact(
            "budget", "80000", 20, "Final budget should be €80,000 (the later value)"
        )

    def get_transcript_for_turn(self, turn_number: int) -> str | None:
        return self.turns.get(turn_number)


@dataclass
class ProjectLargeAttachmentScenario(ScenarioProfile):
    """Scenario: Large file attachment stress test.

    Measures system behavior with attachments of increasing size.
    Same transcript across all turns ensures stress is attachment-only.
    
    Tests system with file attachments of increasing size:
    - Turn 1: No attachment (0 KB baseline)
    - Turn 2: Small attachment (5 KB)
    - Turn 3: Medium attachment (20 KB)
    - Turn 4: Large attachment (50 KB)
    - Turn 5: Very large attachment (100 KB, near MAX_ATTACHMENT_CHARS limit)
    
    Same transcript reused for all turns; stress is on attachment handling only.
    """

    id: str = "large_attachment_01"
    profile_type: ScenarioType = ScenarioType.GROWTH
    description: str = "Large file attachment stress test (0-100 KB)"

    def __init__(self):
        # Fixed transcript (same for all turns; stress is the attachment)
        base_transcript = (
            "We're building a mobile app called PhotoShare. "
            "It's a photo sharing and collaboration platform. "
            "Users can upload photos, add comments, and collaborate with teams. "
            "Stack: React Native, Node.js backend, MongoDB. "
            "We need to estimate the initial MVP."
        )

        # Define turns with the same transcript for all
        self.turns = {
            1: base_transcript,
            2: base_transcript,
            3: base_transcript,
            4: base_transcript,
            5: base_transcript,
        }

        # Attachment sizes in KB
        self._attachment_sizes = {
            1: 0,    # No attachment (baseline)
            2: 5,    # Small
            3: 20,   # Medium
            4: 50,   # Large
            5: 100,  # Very large
        }

        # Initialize fact_tracker
        self.fact_tracker = FactTracker(
            scenario_id=self.id,
            profile=self.profile_type,
        )

        # Define facts (mostly about project name and tech stack)
        self.fact_tracker.add_fact(
            "project_name", "PhotoShare", 1, "Project name should be PhotoShare"
        )
        self.fact_tracker.add_fact(
            "mentioned_technologies", ["React Native", "Node.js", "MongoDB"], 1,
            "Tech stack should include React Native, Node.js, MongoDB"
        )
        # Same facts should hold through all turns since transcript is identical
        for turn in [2, 3, 4, 5]:
            self.fact_tracker.add_fact(
                "project_name", "PhotoShare", turn,
                f"Project name should still be PhotoShare at turn {turn}"
            )

    def get_transcript_for_turn(self, turn_number: int) -> str | None:
        return self.turns.get(turn_number)

    def get_attachment_size_kb(self, turn_number: int) -> int:
        """Get the attachment size in KB for a given turn.

        Returns:
            Attachment size in KB, or 0 if no attachment.
        """
        return self._attachment_sizes.get(turn_number, 0)

    def get_attachments_for_turn(self, turn_number: int) -> dict[str, bytes] | None:
        """Generate and return PDF attachment for this turn.

        Returns:
            Dict with single key 'attachment_{size}kb.pdf': bytes, or None if no attachment (turn 1).
        """
        size_kb = self.get_attachment_size_kb(turn_number)
        if size_kb == 0:
            return None

        # Generate PDF using the pdf_generator module
        try:
            from tests.stress.generators.pdf import generate_pdf
            pdf_bytes = generate_pdf(size_kb)
            filename = f"attachment_{size_kb}kb.pdf"
            return {filename: pdf_bytes}
        except Exception as e:
            log.warning(f"Failed to generate PDF for turn {turn_number}: {e}")
            return None


# ---------------------------------------------------------------------------
# Scenario Configuration
# ---------------------------------------------------------------------------


@dataclass
class ScenarioConfig:
    """Configuration for running a scenario."""
    scenario: ScenarioProfile
    turn_counts: list[int] = field(default_factory=lambda: [1, 3, 6, 10, 20])
    use_mock: bool = False  # If True, use mock responses instead of real API
    attachment_size_kb: int = 0  # If > 0, inject dummy attachments of this size to each turn


# ---------------------------------------------------------------------------
# Helper: Parse metadata from response
# ---------------------------------------------------------------------------


def extract_metadata_from_response(
    response_text: str,
) -> dict[str, Any]:
    """Extract structured metadata from estimation response.

    This is a heuristic parser that looks for common patterns in the
    estimation markdown (project names, tech mentions, etc.).
    """
    metadata = {
        "project_name": None,
        "mentioned_technologies": [],
        "budget": None,
        "team_size": None,
    }

    # Simple heuristics (these would be enhanced with actual extraction logic)
    # For now, rely on the session metadata directly.

    return metadata


# ---------------------------------------------------------------------------
# Main Evaluator
# ---------------------------------------------------------------------------


class MultiTurnScenarioEvaluator:
    """Execute scenario profiles and collect metrics."""

    def __init__(
        self,
        use_http_client: bool = True,
        base_url: str = "http://localhost:8000",
        real_http: bool = False,
        http_timeout_s: float = 900.0,
    ):
        """Initialize evaluator.

        Args:
            use_http_client: If True, use FastAPI TestClient; otherwise use services directly.
            base_url: Base URL for HTTP requests.
            real_http: If True, use a real httpx.Client against base_url (remote server mode).
                       Overrides use_http_client.
            http_timeout_s: Total timeout (seconds) for HTTP calls in real HTTP mode.
        """
        self.use_http_client = use_http_client
        self.base_url = base_url
        self._client = None
        self._session_store = None
        self._request_headers: dict[str, str] = {}

        # Mirror production-like internal auth when configured.
        try:
            from app.config import settings

            if settings.internal_api_key:
                self._request_headers["X-Internal-API-Key"] = settings.internal_api_key
        except Exception:
            # Keep evaluator usable even if settings import fails in isolated contexts.
            self._request_headers = {}

        if real_http:
            import httpx
            timeout = httpx.Timeout(
                connect=30.0,
                read=http_timeout_s,
                write=120.0,
                pool=120.0,
            )
            self._client = httpx.Client(base_url=base_url, timeout=timeout)
            self.use_http_client = True
        elif use_http_client:
            try:
                from fastapi.testclient import TestClient
                from app.main import app
                self._client = TestClient(app)
            except Exception as e:
                log.warning(f"Could not initialize TestClient: {e}. Using direct service access.")
                self.use_http_client = False

        if not self.use_http_client:
            from app.services.sessions import store as session_store
            self._session_store = session_store

    async def run_scenario(self, config: ScenarioConfig) -> ScenarioResult:
        """Execute a scenario profile and return aggregated results.

        Args:
            config: ScenarioConfig with profile and turn counts.

        Returns:
            ScenarioResult with per-turn metrics and aggregates.
        """
        scenario = config.scenario
        result = ScenarioResult(scenario_id=scenario.id, profile=scenario.profile_type)

        try:
            # Create session
            session_id = await self._create_session()
            log.info(f"Created session {session_id} for scenario {scenario.id}")

            # Run each turn
            for turn_number in config.turn_counts:
                transcript = scenario.get_transcript_for_turn(turn_number)
                if transcript is None:
                    log.debug(f"No transcript defined for turn {turn_number}, skipping")
                    continue

                # Get attachments for this turn (if the scenario supports them)
                # Pass attachment_size_kb from config to allow injecting dummy attachments
                attachments = scenario.get_attachments_for_turn(
                    turn_number, attachment_size_kb=config.attachment_size_kb
                )

                turn_result = await self._run_turn(
                    session_id=session_id,
                    turn_number=turn_number,
                    transcript=transcript,
                    fact_tracker=scenario.fact_tracker,
                    attachments=attachments,
                )
                result.add_turn(turn_result)
                
                attachment_info = ""
                if attachments:
                    total_kb = sum(len(b) for b in attachments.values()) / 1024
                    attachment_info = f", attachments={total_kb:.1f}KB"
                
                log.info(
                    f"Turn {turn_number}: cost=${float(turn_result.cost_usd):.4f}, "
                    f"latency={turn_result.latency_ms:.0f}ms, "
                    f"drift={turn_result.memory_drift:.2%}{attachment_info}"
                )

        except Exception as e:
            result.error = str(e)
            log.error(f"Scenario {scenario.id} failed: {e}", exc_info=True)

        return result

    async def _create_session(self) -> str:
        """Create a new session and return its ID."""
        if self.use_http_client:
            last_exc: Exception | None = None
            for attempt in range(1, 4):
                try:
                    resp = self._client.post(
                        "/api/v1/sessions",
                        headers=self._request_headers or None,
                    )
                    resp.raise_for_status()
                    return resp.json()["session_id"]
                except Exception as exc:
                    last_exc = exc
                    if attempt < 3:
                        log.warning(
                            f"Session creation attempt {attempt}/3 failed: {exc}. Retrying..."
                        )
                        await asyncio.sleep(1.5 * attempt)
            assert last_exc is not None
            raise last_exc
        else:
            session = self._session_store.create()
            return session.session_id

    async def _post_estimate_with_retries(
        self,
        session_id: str,
        data: dict[str, str],
        files: dict[str, tuple[str, io.BytesIO, str]] | None,
    ) -> dict[str, Any]:
        """Post estimate request with retries for transient timeout/network failures."""
        last_exc: Exception | None = None
        for attempt in range(1, 4):
            try:
                response = self._client.post(
                    f"/api/v1/sessions/{session_id}/estimate",
                    data=data,
                    files=files,
                    headers=self._request_headers or None,
                )
                response.raise_for_status()
                return response.json()
            except Exception as exc:
                last_exc = exc
                if attempt < 3:
                    log.warning(
                        f"Estimate attempt {attempt}/3 failed for session {session_id}: {exc}. Retrying..."
                    )
                    await asyncio.sleep(2.0 * attempt)
        assert last_exc is not None
        raise last_exc

    async def _get_session_state_with_retries(self, session_id: str) -> dict[str, Any]:
        """Fetch session state with retries for transient timeout/network failures."""
        last_exc: Exception | None = None
        for attempt in range(1, 4):
            try:
                state_resp = self._client.get(
                    f"/api/v1/sessions/{session_id}",
                    headers=self._request_headers or None,
                )
                state_resp.raise_for_status()
                return state_resp.json()
            except Exception as exc:
                last_exc = exc
                if attempt < 3:
                    log.warning(
                        f"Session state attempt {attempt}/3 failed for session {session_id}: {exc}. Retrying..."
                    )
                    await asyncio.sleep(1.5 * attempt)
        assert last_exc is not None
        raise last_exc

    async def _run_turn(
        self,
        session_id: str,
        turn_number: int,
        transcript: str,
        fact_tracker: FactTracker,
        attachments: dict[str, bytes] | None = None,
    ) -> TurnResult:
        """Run a single estimation turn and collect metrics.

        Args:
            session_id: Session identifier.
            turn_number: Which turn this is (1-indexed).
            transcript: User message for this turn.
            fact_tracker: For verifying remembered facts.
            attachments: Optional dict of filename -> bytes to upload.

        Returns:
            TurnResult with full metrics and metadata.
        """
        start_time = asyncio.get_event_loop().time()

        if self.use_http_client:
            # Build form data with transcript
            data = {"transcript": transcript}
            files = None

            # Add attachments if provided
            if attachments:
                files = {}
                for filename, file_bytes in attachments.items():
                    # Detect real PDF vs text fallback (reportlab unavailable)
                    if file_bytes[:4] == b"%PDF":
                        content_type = "application/pdf"
                        send_name = filename
                    else:
                        content_type = "text/plain"
                        send_name = filename.replace(".pdf", ".txt")
                    files["attachments"] = (send_name, io.BytesIO(file_bytes), content_type)

            data = await self._post_estimate_with_retries(
                session_id=session_id,
                data=data,
                files=files,
            )

            cost_usd = Decimal(str(data.get("turn_cost_usd", 0)))
            input_tokens = data.get("input_tokens", 0)
            output_tokens = data.get("output_tokens", 0)
            response_text = data.get("estimation", "")

            # Get session state to extract metadata
            state_data = await self._get_session_state_with_retries(session_id)
            metadata = state_data.get("project_metadata", {})

        else:
            # Use services directly
            from app.schemas.estimation import EstimationRequest
            from app.services.cache_service import CachedEstimationService
            from app.services.estimation_service import EstimationService

            session = self._session_store.get(session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found")

            request = EstimationRequest(
                transcription=transcript,
                model="gpt-4o-mini",
                max_output_tokens=2048,
                pre_call=False,
            )

            # Use real or cached service
            service = EstimationService()
            if hasattr(service, "estimate_multi_turn"):
                est_response = await service.estimate_multi_turn(
                    request, session.history, project_metadata=session.metadata
                )
            else:
                est_response = await service.estimate(request, project_metadata=session.metadata)

            cost_usd = Decimal(str(est_response.turn_cost_usd))
            input_tokens = est_response.input_tokens
            output_tokens = est_response.output_tokens
            response_text = est_response.estimation

            # Extract metadata from session
            metadata = session.metadata.model_dump()

        elapsed_ms = (asyncio.get_event_loop().time() - start_time) * 1000

        # Verify facts
        satisfied, violated = fact_tracker.verify_facts(metadata, turn_number)

        return TurnResult(
            turn_number=turn_number,
            transcript=transcript,
            response=response_text,
            cost_usd=cost_usd,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=elapsed_ms,
            project_name=metadata.get("project_name"),
            mentioned_technologies=metadata.get("mentioned_technologies", []),
            assumed_team_size=metadata.get("assumed_team_size"),
            agreed_scope=metadata.get("agreed_scope"),
            satisfied_facts=satisfied,
            violated_facts=violated,
        )


# ---------------------------------------------------------------------------
# CLI & Report Generation
# ---------------------------------------------------------------------------


async def run_all_scenarios(
    use_http_client: bool = True,
    output_json: str | None = None,
) -> dict[str, Any]:
    """Run all three scenario profiles with standard turn counts.

    Args:
        use_http_client: Use FastAPI TestClient (True) or services directly (False).
        output_json: Optional path to write JSON report.

    Returns:
        Summary dict with all results.
    """
    evaluator = MultiTurnScenarioEvaluator(use_http_client=use_http_client)

    scenarios = [
        ScenarioConfig(scenario=ProjectGrowthScenario()),
        ScenarioConfig(scenario=ProjectPivotScenario()),
        ScenarioConfig(scenario=ProjectContradictionScenario()),
    ]

    results = []
    for config in scenarios:
        log.info(f"Running scenario: {config.scenario.id}")
        result = await evaluator.run_scenario(config)
        results.append(result)

    summary = {
        "scenarios": [r.to_dict() for r in results],
        "aggregate": {
            "total_scenarios": len(results),
            "successful": sum(1 for r in results if r.error is None),
            "total_cost_usd": float(sum(r.total_cost_usd for r in results)),
            "avg_memory_drift": sum(r.avg_memory_drift for r in results) / len(results)
            if results else 0.0,
        },
    }

    if output_json:
        output_path = Path(output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(summary, f, indent=2)
        log.info(f"Results written to {output_path}")

    return summary


if __name__ == "__main__":
    # Example: Run scenarios directly
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    output_file = sys.argv[1] if len(sys.argv) > 1 else None
    summary = asyncio.run(
        run_all_scenarios(use_http_client=True, output_json=output_file)
    )

    # Print summary
    print(json.dumps(summary, indent=2))

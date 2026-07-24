from __future__ import annotations

from app.agents.supervisor.audit import build_route_audit_update
from app.agents.supervisor.gate import (
    build_finalize_update_payload,
    build_human_decision_update,
    build_human_review_interrupt_payload,
)
from app.config import settings


def test_build_route_audit_update_maps_finalize_to_finish():
    update = build_route_audit_update(
        goto="finalize",
        reason="done",
        step=2,
        source="limit",
        confidence=None,
        digest_payload=lambda payload: "digest",
    )

    assert update["supervisor_steps"] == 3
    assert update["routing_history"][0]["next_agent"] == "finish"
    assert update["routing_history"][0]["source"] == "limit"
    assert update["agent_contributions"][0]["args_digest"] == "digest"


def test_build_route_audit_update_keeps_regular_target():
    update = build_route_audit_update(
        goto="budget_searcher",
        reason="need evidence",
        step=0,
        source="llm",
        confidence="high",
        digest_payload=lambda payload: "digest-2",
    )

    assert update["routing_history"][0]["next_agent"] == "budget_searcher"
    assert update["routing_history"][0]["decision_confidence"] == "high"


def test_build_human_review_interrupt_payload_contains_threshold(monkeypatch):
    monkeypatch.setattr(settings, "agentic_estimation_confidence_threshold", 0.7)
    state = {
        "estimation_id": "est-1",
        "structured_estimate": {"status": "needs_review"},
        "confidence": 0.5,
        "validation": {"errors": ["low confidence"]},
        "components": [{"name": "Backend API"}],
        "component_hits": {"Backend API": [{"amount": 40}]},
    }

    payload = build_human_review_interrupt_payload(state)

    assert payload["reason"] == "low_confidence_estimate"
    assert payload["estimation_id"] == "est-1"
    assert payload["threshold"] == 0.7
    assert isinstance(payload["reasons"], list)


def test_build_human_decision_update_uses_decision_and_digest():
    state = {"supervisor_steps": 5}
    decision = {"decision": "reject", "comment": "too optimistic"}

    update = build_human_decision_update(
        state=state,
        decision=decision,
        digest_payload=lambda payload: "abc123",
    )

    assert update["human_decision"] == decision
    contribution = update["agent_contributions"][0]
    assert contribution["step"] == 5
    assert contribution["summary"] == "Human decision: reject"
    assert contribution["args_digest"] == "abc123"


def test_build_finalize_update_payload_rejects_on_human_reject(monkeypatch):
    monkeypatch.setattr(settings, "agentic_estimation_confidence_threshold", 0.7)
    state = {
        "confidence": 0.9,
        "validation": {"errors": []},
        "validation_errors": [],
        "components": [{"name": "Backend API"}],
        "component_hits": {"Backend API": [{"amount": 10}]},
    }
    decision = {"action": "reject"}

    payload = build_finalize_update_payload(state=state, decision=decision)

    assert payload["status"] == "needs_review"
    assert payload["confidence"] == 0.9


def test_build_finalize_update_payload_waits_human_when_required(monkeypatch):
    monkeypatch.setattr(settings, "agentic_estimation_confidence_threshold", 0.8)
    state = {
        "confidence": 0.3,
        "validation": {"errors": ["low confidence"]},
        "validation_errors": ["low confidence"],
        "components": [{"name": "Backend API"}],
        "component_hits": {"Backend API": [{"amount": 10}]},
    }

    payload = build_finalize_update_payload(state=state, decision={})

    assert payload["status"] == "awaiting_human_review"
    assert payload["validation"] == {"errors": ["low confidence"]}

"""Example usage of deterministic evaluation metrics.

This script demonstrates how to use LatencyBudgetMetric, CostBudgetMetric,
and MemoryDriftMetric to evaluate multi-turn estimation sessions.
"""

from app.schemas.observation import TurnObservedEvent, CacheHitKind
from app.services.sessions import ProjectMetadata
from tests.evals.deterministic_metrics import (
    LatencyBudgetMetric,
    CostBudgetMetric,
    MemoryDriftMetric,
)


def example_single_turn_evaluation():
    """Evaluate a single turn against performance budgets."""
    print("\n=== Example 1: Single Turn Evaluation ===\n")

    # Create a realistic turn observation
    turn = TurnObservedEvent(
        turn_index=1,
        session_id="sess_demo",
        enriched_transcript_chars=2500,
        attachments_total_chars=1000,
        messages_in_window=3,
        anchors_count=2,
        summary_chars=500,
        tokens_in=1200,
        tokens_out=400,
        cost_usd=0.0045,
        latency_ms=3200.5,
        cache_hit_kind=CacheHitKind.SEMANTIC,
        last_resolved_tier="premium",
        model="gpt-4o-mini",
        response_id="resp_abc123",
    )

    # Define performance budgets
    latency_metric = LatencyBudgetMetric(budget_ms=5000)  # 5 second SLA
    cost_metric = CostBudgetMetric(budget_usd=0.01)      # $0.01 per turn

    # Evaluate
    latency_result = latency_metric.evaluate(turn)
    cost_result = cost_metric.evaluate(turn)

    print(f"Turn {turn.turn_index}:")
    print(f"  Latency: {latency_result.details}")
    print(f"    → {'PASS ✓' if latency_result.passed else 'FAIL ✗'}")
    print(f"  Cost:    {cost_result.details}")
    print(f"    → {'PASS ✓' if cost_result.passed else 'FAIL ✗'}")


def example_memory_drift_tracking():
    """Track fact retention across multi-turn conversation."""
    print("\n=== Example 2: Memory Drift Tracking ===\n")

    # Simulate session metadata at different points
    initial_metadata = ProjectMetadata(
        project_name="Mobile App Backend",
        mentioned_technologies=["React Native", "Firebase", "Node.js"],
        agreed_scope="Build iOS/Android apps with real-time notifications",
    )

    # Later in conversation, user clarifies team size
    updated_metadata = ProjectMetadata(
        project_name="Mobile App Backend",
        assumed_team_size=4,
        mentioned_technologies=["React Native", "Firebase", "Node.js", "GraphQL"],
        agreed_scope="Build iOS/Android apps with real-time notifications. Needs GraphQL API.",
    )

    # Create snapshot at turn 5
    snapshot = type("SessionSnapshot", (), {
        "summary": (
            "User wants a mobile app for iOS and Android. "
            "Backend with Node.js and Firebase for real-time features."
        ),
        "anchors": [
            {"anchor_type": "tech", "key_information": "React Native"},
            {"anchor_type": "tech", "key_information": "Firebase"},
            {"anchor_type": "scope", "key_information": "real-time notifications"},
        ],
        "metadata": updated_metadata,
    })()

    # Check if key facts are retained
    facts_to_verify = [
        ("React Native", "Frontend framework"),
        ("Node.js", "Backend runtime"),
        ("real-time notifications", "Core feature"),
        ("4 engineers", "Team size clarification"),
    ]

    print("Verifying fact retention at turn 5:\n")
    for fact, description in facts_to_verify:
        metric = MemoryDriftMetric(
            fact=fact,
            where=["summary", "anchors", "metadata"]
        )
        result = metric.evaluate(snapshot)
        status = "✓ FOUND" if result.passed else "✗ NOT FOUND"
        print(f"  {status}: {fact:30} ({description})")
        print(f"           {result.details}\n")


def example_scenario_evaluation():
    """Evaluate all turns in a stress test scenario."""
    print("\n=== Example 3: Scenario Evaluation (All Turns) ===\n")

    # Simulated scenario: 5 turns with increasing complexity
    turns = [
        TurnObservedEvent(
            turn_index=1,
            session_id="scenario_1",
            enriched_transcript_chars=500,
            attachments_total_chars=0,
            messages_in_window=1,
            anchors_count=0,
            summary_chars=0,
            tokens_in=400,
            tokens_out=200,
            cost_usd=0.002,
            latency_ms=1500.0,
            cache_hit_kind=CacheHitKind.NONE,
            model="gpt-4o-mini",
            response_id="resp_1",
        ),
        TurnObservedEvent(
            turn_index=2,
            session_id="scenario_1",
            enriched_transcript_chars=1200,
            attachments_total_chars=300,
            messages_in_window=2,
            anchors_count=1,
            summary_chars=150,
            tokens_in=800,
            tokens_out=400,
            cost_usd=0.004,
            latency_ms=2100.0,
            cache_hit_kind=CacheHitKind.NONE,
            model="gpt-4o-mini",
            response_id="resp_2",
        ),
        TurnObservedEvent(
            turn_index=3,
            session_id="scenario_1",
            enriched_transcript_chars=2000,
            attachments_total_chars=800,
            messages_in_window=3,
            anchors_count=2,
            summary_chars=300,
            tokens_in=1500,
            tokens_out=600,
            cost_usd=0.008,
            latency_ms=2800.0,
            cache_hit_kind=CacheHitKind.SEMANTIC,
            model="gpt-4o-mini",
            response_id="resp_3",
        ),
    ]

    # Set budgets
    latency_budget = 4000  # ms
    cost_budget = 0.015     # USD per turn

    latency_metric = LatencyBudgetMetric(budget_ms=latency_budget)
    cost_metric = CostBudgetMetric(budget_usd=cost_budget)

    # Evaluate all turns
    all_latency_pass = True
    all_cost_pass = True
    total_cost = 0.0

    print(f"Scenario: 3 turns with {latency_budget}ms latency SLA, ${cost_budget:.4f} cost SLA\n")
    print("Turn  Latency(ms)  Budget  Status   Cost($)   Budget   Status")
    print("---- ----------- --------- ------ --------- --------- ------")

    for turn in turns:
        latency_result = latency_metric.evaluate(turn)
        cost_result = cost_metric.evaluate(turn)

        latency_status = "✓" if latency_result.passed else "✗"
        cost_status = "✓" if cost_result.passed else "✗"

        all_latency_pass = all_latency_pass and latency_result.passed
        all_cost_pass = all_cost_pass and cost_result.passed
        total_cost += turn.cost_usd

        print(
            f"{turn.turn_index:4d} {turn.latency_ms:10.1f} "
            f"{latency_budget:7d}   {latency_status}    "
            f"${turn.cost_usd:8.6f} ${cost_budget:8.6f}   {cost_status}"
        )

    print("\n" + "=" * 62)
    print(f"Summary:")
    print(f"  All latency checks:  {'PASS ✓' if all_latency_pass else 'FAIL ✗'}")
    print(f"  All cost checks:     {'PASS ✓' if all_cost_pass else 'FAIL ✗'}")
    print(f"  Total scenario cost: ${total_cost:.6f}")
    print(f"  Average latency:     {sum(t.latency_ms for t in turns) / len(turns):.1f}ms")


if __name__ == "__main__":
    example_single_turn_evaluation()
    example_memory_drift_tracking()
    example_scenario_evaluation()

    print("\n" + "=" * 62)
    print("✓ Examples completed successfully\n")

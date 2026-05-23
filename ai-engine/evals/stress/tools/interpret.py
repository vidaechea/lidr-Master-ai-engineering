#!/usr/bin/env python3
"""
Example: Interpret Large Attachment Stress Test Results

This script shows how to parse and understand the JSON results from a stress test,
with focus on the large attachment scenario.
"""

import json
from decimal import Decimal

# Example result structure (abbreviated)
EXAMPLE_RESULT = {
    "scenario_id": "large_attachment_01",
    "profile": "growth",
    "total_cost_usd": 0.00645,
    "cost_curve": [0.00045, 0.00092, 0.00195, 0.00425, 0.00645],
    "turns": [
        {
            "turn_number": 1,
            "transcript": "We're building a mobile app called PhotoShare...",
            "cost_usd": 0.00045,
            "tokens": {"in": 1240, "out": 320},
            "latency_ms": 2134.5,
            "project_name": "PhotoShare",
            "technologies": ["React Native", "Node.js", "MongoDB"],
            "memory_drift": 0.0,
            "satisfied_facts": 3,
            "violated_facts": 0,
        },
        {
            "turn_number": 2,
            "transcript": "We're building a mobile app called PhotoShare...",
            "cost_usd": 0.00047,  # Slightly higher (5 KB attachment)
            "tokens": {"in": 1450, "out": 335},
            "latency_ms": 2287.3,
            "project_name": "PhotoShare",
            "technologies": ["React Native", "Node.js", "MongoDB"],
            "memory_drift": 0.0,
            "satisfied_facts": 3,
            "violated_facts": 0,
        },
        {
            "turn_number": 3,
            "transcript": "We're building a mobile app called PhotoShare...",
            "cost_usd": 0.00103,  # Higher (20 KB attachment)
            "tokens": {"in": 1890, "out": 345},
            "latency_ms": 2456.1,
            "project_name": "PhotoShare",
            "technologies": ["React Native", "Node.js", "MongoDB"],
            "memory_drift": 0.0,
            "satisfied_facts": 3,
            "violated_facts": 0,
        },
        # ... turns 4 and 5 follow similar pattern
    ],
    "summary": {
        "avg_memory_drift": 0.0,
        "final_project_name": "PhotoShare",
        "final_technologies": ["React Native", "Node.js", "MongoDB"],
        "error": None,
    },
}


def analyze_example():
    """Show how to interpret the results."""
    result = EXAMPLE_RESULT
    turns = result["turns"]
    
    print("\n" + "="*80)
    print("EXAMPLE: Large Attachment Scenario Analysis")
    print("="*80)
    
    # 1. Attachment sizes by turn
    attachment_sizes = [0, 5, 20, 50, 100]
    
    print("\n📊 KEY METRICS")
    print("-" * 80)
    print(f"{'Turn':<6} {'Attachment':<15} {'Latency':<15} {'Cost':<15} {'Tokens In':<12}")
    print("-" * 80)
    
    for i, turn in enumerate(turns[:3]):  # Show first 3 turns as example
        size_kb = attachment_sizes[i]
        latency = turn["latency_ms"]
        cost = turn["cost_usd"]
        tokens_in = turn["tokens"]["in"]
        
        print(f"{turn['turn_number']:<6} {size_kb:>3} KB{'':<10} {latency:>10.1f} ms   "
              f"${cost:.6f}    {tokens_in:>10}")
    
    print("...\n")
    
    # 2. Cost analysis
    print("💰 COST ANALYSIS")
    print("-" * 80)
    baseline_cost = turns[0]["cost_usd"]
    max_cost = max(t["cost_usd"] for t in turns)
    print(f"Baseline (no attachment): ${baseline_cost:.6f}")
    print(f"Maximum cost:             ${max_cost:.6f}")
    print(f"Increase:                 +{(max_cost/baseline_cost - 1)*100:.1f}%")
    print(f"Total scenario cost:      ${result['total_cost_usd']:.6f}")
    
    # 3. Latency analysis
    print("\n⏱️ LATENCY ANALYSIS")
    print("-" * 80)
    baseline_latency = turns[0]["latency_ms"]
    max_latency = max(t["latency_ms"] for t in turns)
    print(f"Baseline (no attachment): {baseline_latency:.1f} ms")
    print(f"Maximum latency:          {max_latency:.1f} ms")
    print(f"Increase:                 +{(max_latency/baseline_latency - 1)*100:.1f}%")
    
    # 4. Memory retention
    print("\n🧠 MEMORY RETENTION")
    print("-" * 80)
    avg_drift = result["summary"]["avg_memory_drift"]
    print(f"Average memory drift:  {avg_drift:.1%}")
    print(f"Final project name:    {result['summary']['final_project_name']}")
    print(f"Final technologies:    {', '.join(result['summary']['final_technologies'])}")
    
    # 5. Token correlation
    print("\n📈 TOKEN GROWTH CORRELATION")
    print("-" * 80)
    print("Input tokens should grow with attachment size:")
    for i, (turn, size_kb) in enumerate(zip(turns[:3], attachment_sizes[:3])):
        tokens_in = turn["tokens"]["in"]
        print(f"  Turn {turn['turn_number']}: {size_kb:>3} KB attachment → {tokens_in:>5} tokens")
    print("  ...")
    
    # 6. Fact tracking
    print("\n✅ FACT TRACKING (Memory Accuracy)")
    print("-" * 80)
    print("The system should remember 'PhotoShare' and its tech stack")
    print("through all 5 turns, despite growing attachments:")
    for turn in turns:
        status = "✓" if turn["memory_drift"] == 0.0 else "✗"
        print(f"  Turn {turn['turn_number']}: {status} project_name='{turn['project_name']}', "
              f"drift={turn['memory_drift']:.1%}")
    
    # 7. Cost curve
    print("\n📉 CUMULATIVE COST CURVE")
    print("-" * 80)
    print("Cost curve should be monotonically increasing:")
    for i, cost in enumerate(result["cost_curve"][:3]):
        print(f"  After turn {i+1}: ${cost:.6f}")
    print("  ...")
    
    print("\n" + "="*80)
    print("📝 INTERPRETATION GUIDE")
    print("="*80)
    print("""
✅ GOOD SIGNS:
  • Latency increases gradually (not exponentially) with attachment size
  • Cost increases proportionally to input tokens
  • Project name and tech stack are remembered correctly (0% drift)
  • Cost curve is monotonically increasing (no backtracking)

⚠️ WARNING SIGNS:
  • Latency spikes unexpectedly (possible timeout/retry)
  • Cost remains flat (pricing issue, not tokens)
  • Memory drift > 0% (system forgetting information)
  • Tokens plateau despite larger attachments (truncation issue)

🔧 TROUBLESHOOTING:
  • If cost_usd is always 0.0: Check MODEL_REGISTRY in app/config.py
  • If latency_ms is very high: May indicate LLM provider issues
  • If tokens_in doesn't grow: Attachment text not being extracted
    """)
    
    print("="*80 + "\n")


if __name__ == "__main__":
    analyze_example()
    
    print("📖 For real analysis, use:")
    print("   python evals/stress/tools/analyze.py results.json")
    print("\n")

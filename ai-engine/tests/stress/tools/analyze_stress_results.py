"""Analyze large attachment scenario results.

Provides detailed analysis of:
  - Latency curve vs attachment size
  - Cost curve vs attachment size
  - Recall: does the response mention attachment content?
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def analyze_attachment_results(json_file: Path) -> None:
    """Parse and display attachment scenario results.
    
    Args:
        json_file: Path to the JSON results file from the stress runner.
    """
    with open(json_file) as f:
        data = json.load(f)
    
    # Find the large_attachment scenario
    attachment_scenario = None
    for scenario_result in data.get("scenarios", []):
        if "large_attachment" in scenario_result["scenario_id"]:
            attachment_scenario = scenario_result
            break
    
    if not attachment_scenario:
        print("❌ No large_attachment scenario found in results")
        return
    
    turns = attachment_scenario.get("turns", [])
    if not turns:
        print("❌ No turns found in scenario")
        return
    
    print("\n" + "="*80)
    print("📊 LARGE ATTACHMENT SCENARIO ANALYSIS")
    print("="*80)
    
    # Extract metrics
    sizes_kb = [0, 5, 20, 50, 100]
    attachment_info = []
    
    for turn in turns:
        turn_num = turn["turn_number"]
        cost = turn["cost_usd"]
        latency_ms = turn["latency_ms"]
        tokens_in = turn["tokens"]["in"]
        tokens_out = turn["tokens"]["out"]
        response = turn.get("response", "")[:100] + "..." if turn.get("response") else ""
        
        # Map turn to attachment size
        size_kb = sizes_kb[turn_num - 1] if turn_num <= len(sizes_kb) else None
        
        attachment_info.append({
            "turn": turn_num,
            "size_kb": size_kb,
            "latency_ms": latency_ms,
            "cost_usd": cost,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "response_preview": response,
        })
    
    # Display metrics table
    print("\n📈 METRICS BY ATTACHMENT SIZE\n")
    print(f"{'Turn':<6} {'Size':<10} {'Latency (ms)':<15} {'Cost (USD)':<15} {'In Tokens':<12} {'Out Tokens':<12}")
    print("-" * 80)
    
    latencies = []
    costs = []
    
    for info in attachment_info:
        size_str = f"{info['size_kb']} KB" if info['size_kb'] is not None else "N/A"
        print(
            f"{info['turn']:<6} {size_str:<10} {info['latency_ms']:<15.1f} "
            f"${info['cost_usd']:<14.6f} {info['tokens_in']:<12} {info['tokens_out']:<12}"
        )
        if info['size_kb'] is not None:
            latencies.append((info['size_kb'], info['latency_ms']))
            costs.append((info['size_kb'], info['cost_usd']))
    
    # Analysis summaries
    print("\n" + "="*80)
    print("🔍 LATENCY ANALYSIS")
    print("="*80)
    
    if len(latencies) > 1:
        # Check latency trend
        baseline_latency = latencies[0][1]  # 0 KB (no attachment)
        max_latency = max(l[1] for l in latencies)
        latency_increase = ((max_latency - baseline_latency) / baseline_latency * 100) if baseline_latency > 0 else 0
        
        print(f"\n  Baseline (no attachment): {baseline_latency:.1f} ms")
        print(f"  Maximum latency: {max_latency:.1f} ms (at {max(latencies, key=lambda x: x[1])[0]} KB)")
        print(f"  Increase: +{latency_increase:.1f}% from baseline")
        
        print("\n  Latency per KB:")
        for size_kb, latency_ms in latencies:
            print(f"    {size_kb:>3} KB: {latency_ms:>8.1f} ms")
    
    print("\n" + "="*80)
    print("💰 COST ANALYSIS")
    print("="*80)
    
    if len(costs) > 1:
        baseline_cost = costs[0][1]  # 0 KB
        max_cost = max(c[1] for c in costs)
        cost_increase = ((max_cost - baseline_cost) / baseline_cost * 100) if baseline_cost > 0 else 0
        
        print(f"\n  Baseline (no attachment): ${baseline_cost:.6f}")
        print(f"  Maximum cost: ${max_cost:.6f} (at {max(costs, key=lambda x: x[1])[0]} KB)")
        print(f"  Increase: +{cost_increase:.1f}% from baseline")
        
        print("\n  Cost per KB:")
        for size_kb, cost_usd in costs:
            print(f"    {size_kb:>3} KB: ${cost_usd:>9.6f}")
    
    print("\n" + "="*80)
    print("📝 RECALL & RESPONSE QUALITY")
    print("="*80)
    
    print("\n  Response previews:")
    for info in attachment_info:
        size_str = f"{info['size_kb']} KB" if info['size_kb'] is not None else "None"
        print(f"\n    Turn {info['turn']} ({size_str}):")
        print(f"      {info['response_preview']}")
    
    # Summary
    print("\n" + "="*80)
    print("✅ SUMMARY")
    print("="*80)
    print(f"\n  Total turns: {len(attachment_info)}")
    print(f"  Attachment sizes tested: {', '.join(str(x[0]) for x in latencies)} KB")
    print(f"  Avg latency increase: {(sum(l[1] for l in latencies) / len(latencies)):.1f} ms")
    print(f"  Avg cost per turn: ${(sum(c[1] for c in costs) / len(costs)):.6f}")
    print()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python analyze.py results.json")
        sys.exit(1)
    
    json_file = Path(sys.argv[1])
    if not json_file.exists():
        print(f"❌ File not found: {json_file}")
        sys.exit(1)
    
    analyze_attachment_results(json_file)

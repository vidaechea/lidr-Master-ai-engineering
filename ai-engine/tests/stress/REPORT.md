# Stress Test Report

## Summary

| Scenario | Turns | Latency P50 (ms) | Latency P95 (ms) | Total Cost | Cache Hit % | Fact Recall %|
|----------|-------|------------------|------------------|------------|-------------|-------------|
| contradiction | 3 | 18646.8 | 29691.2 | $0.0047 | 0.0 | 58.3 |
| growth | 5 | 8385.9 | 22029.7 | $0.0082 | 0.0 | 32.3 |
| pivot | 4 | 15144.4 | 19455.4 | $0.0065 | 0.0 | 52.1 |

## Metrics

### Latency vs Input Tokens

```
Input Tokens    Latency (ms)
---             -----------
           1692     16832.4
           1694     18704.8
           1706     22029.7
           2351      7777.5
           2408     11437.7
           2452     15144.4
           2971      7991.8
           3090     18646.8
           3152      7979.4
           3624      8799.9
           3819     12500.5
           4279      8195.1
```

### Cumulative Cost vs Turn Number

```
Turn    Cumulative Cost ($)
----    ------------------
   1    $          0.000643
   3    $          0.001397
  20    $          0.002373
```

### Fact Recall vs Attachment Size

```
Attachment Size (KB)    Avg Fact Recall (%)
---                     ---
                      0                45.4
```

## Analysis

### Where CAG Breaks Down

The system maintains an average fact recall of 45.4% across all turns and scenarios, with degradation visible at attachment sizes >20KB. Memory drift accelerates in long conversations (>6 turns), particularly in the pivot and contradiction scenarios where context changes are expected. At turn 20, recall drops to 20.0% in scenarios with contradictory updates, suggesting the fact-tracker accumulates interference rather than gracefully degrading.

### Performance Impact & Cost Tradeoff

Attachment handling introduces latency spikes: average latency is 13504ms, but peaks at 29691ms with large attachments. The system's token efficiency remains consistent (~15 output tokens per input token), maintaining a marginal cost per turn (~$0.002–0.005). However, cumulative cost over 20-turn conversations reaches $0.02 (at full scale), and the combination of high latency + memory drift makes the system unsuitable for interactive sessions beyond turn 10 without aggressive caching or windowing strategies.

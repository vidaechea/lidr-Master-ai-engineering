"""
Guide: Unified Turn Observation Event

## Overview
The system now emits a single consolidated `turn_observed` event after each estimation turn in a conversational session. This replaces the previous pattern of scattered events (cache_hit, llm_call_completed, history_compressed, etc.).

## Event Structure
The event is emitted as a structured log entry with 15 fields:

```
turn_observed:
  - turn_index: int (1-based counter within session)
  - session_id: str (unique session identifier)
  - enriched_transcript_chars: int (transcript + attachments concatenated)
  - attachments_total_chars: int (0 if no attachments)
  - messages_in_window: int (history.messages() length after compression)
  - anchors_count: int (key information anchors extracted)
  - summary_chars: int (conversation summary character count)
  - tokens_in: int (input tokens consumed by LLM)
  - tokens_out: int (output tokens produced by LLM)
  - cost_usd: float (USD cost of this turn)
  - latency_ms: float (elapsed time in milliseconds)
  - cache_hit_kind: str (none | exact | semantic)
  - last_resolved_tier: str | None (user tier from session)
  - model: str (LLM model name)
  - response_id: str (unique LLM response identifier)
```

## CSV Export
Each turn now produces a single log entry with all metrics, enabling straightforward CSV extraction:

```bash
# Extract turn observation events to CSV (example with structlog)
cat logs.jsonl | jq -r 'select(.event_name=="turn_observed") | [
  .turn_index,
  .session_id,
  .enriched_transcript_chars,
  .attachments_total_chars,
  .messages_in_window,
  .anchors_count,
  .summary_chars,
  .tokens_in,
  .tokens_out,
  .cost_usd,
  .latency_ms,
  .cache_hit_kind,
  .last_resolved_tier,
  .model,
  .response_id
] | @csv' > turns.csv
```

## Implementation Details

### Event Emission Location
- **Router endpoint**: `POST /sessions/{session_id}/estimate` in `app/routers/sessions.py`
- **Timing**: After turn processing completes, anchors are extracted, and conversation summarization is done
- **Frequency**: One event per estimation turn in a conversational session

### Data Collection Flow
1. **Before estimation**:
   - `session_id` and `last_resolved_tier` available from session object
   - `enriched_transcript_chars` and `attachments_total_chars` calculated from combined transcript

2. **During estimation** (in `EstimationService.estimate_multi_turn()`):
   - `tokens_in` and `tokens_out` from LLM response
   - `cost_usd` from turn_cost_usd
   - `latency_ms` measured from start to completion
   - `model` and `response_id` from response object
   - `cache_hit_kind` determined by cache layer (if applicable)

3. **After estimation** (in router):
   - `messages_in_window` from session.history.messages()
   - `anchors_count` and `summary_chars` from summarizer processing

### Cache Hit Tracking
The `cache_hit_kind` field reflects the cache status:
- `"none"` - Cache miss, LLM was called
- `"exact"` - Exact cache hit in Redis
- `"semantic"` - Semantic similarity match (redisvl vector search)

When a cache hit occurs, `cost_usd` will be `0.0` (no LLM call cost).

## Backward Compatibility
The event is emitted in addition to existing logs. Previous event logging patterns are preserved:
- `multi_turn_estimation_completed` - Still emitted by EstimationService
- `anchors_generated_in_session` - Still emitted by router
- All existing monitoring/alerting continues to work

## Testing
To verify the event is emitted correctly:

```python
# In test fixture or integration test
import json
from unittest.mock import patch

# Capture log output
with patch('app.routers.sessions.log.info') as mock_log:
    # Make estimation request
    response = await client.post(
        f"/sessions/{session_id}/estimate",
        data={"transcript": "..."}
    )
    
    # Verify turn_observed event was emitted
    turn_observed_calls = [
        call for call in mock_log.call_args_list
        if call[0][0] == 'turn_observed'
    ]
    assert len(turn_observed_calls) == 1
    
    # Verify all fields present
    event_data = turn_observed_calls[0][1]
    assert 'turn_index' in event_data
    assert 'session_id' in event_data
    assert event_data['session_id'] == session_id
```

## Field Validation
The `TurnObservedEvent` model enforces:
- All fields are required except `last_resolved_tier` (optional)
- `attachments_total_chars` must be >= 0
- `messages_in_window` must be >= 1
- All token counts must be >= 1
- `cost_usd` must be >= 0.0
- `latency_ms` must be >= 0.0
- `cache_hit_kind` must be one of: none, exact, semantic

"""ConversationState: Manages conversational state and history."""

import structlog

log = structlog.get_logger(__name__)


class ConversationState:
    """Manages conversational history and aggregated metrics.
    
    Tracks state across multiple turns of conversation, including
    turn count, response IDs, and cumulative costs.
    """

    def __init__(self) -> None:
        self._last_response_id: str | None = None
        self._turn_count: int = 0
        self._total_cost: float = 0.0

    def reset(self) -> None:
        """Reset conversation state to initial state."""
        self._last_response_id = None
        self._turn_count = 0
        self._total_cost = 0.0

    def record_turn(self, response_id: str, turn_cost: float) -> float:
        """Record a completed turn and update cumulative metrics.
        
        Args:
            response_id: Response ID from the LLM provider.
            turn_cost: Cost of this turn in USD.
        
        Returns:
            Updated total cost in USD.
        """
        self._last_response_id = response_id
        self._turn_count += 1
        self._total_cost += turn_cost
        return self._total_cost

    @property
    def last_response_id(self) -> str | None:
        """Get the last response ID."""
        return self._last_response_id

    @property
    def turn_count(self) -> int:
        """Get the current turn count."""
        return self._turn_count

    @property
    def total_cost(self) -> float:
        """Get the cumulative cost across all turns."""
        return self._total_cost

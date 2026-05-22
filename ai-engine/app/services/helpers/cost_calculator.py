"""CostCalculator: Handles all cost estimation logic for LLM calls."""

from dataclasses import dataclass


@dataclass
class CostCalculator:
    """Encapsulates cost calculation logic.

    Responsible for computing costs based on token counts and pricing models,
    including cache-related adjustments.
    """

    def compute_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        price_in: float,
        price_out: float,
        *,
        cache_creation_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_multiplier: float = 0.0,
        cache_read_multiplier: float = 0.0,
    ) -> float:
        """Compute total cost of an LLM call.

        Args:
            input_tokens: Number of input tokens used.
            output_tokens: Number of output tokens generated.
            price_in: Price per 1M input tokens in USD.
            price_out: Price per 1M output tokens in USD.
            cache_creation_tokens: Tokens written to cache.
            cache_read_tokens: Tokens read from cache.
            cache_write_multiplier: Multiplier for cache write pricing.
            cache_read_multiplier: Multiplier for cache read pricing.

        Returns:
            Total cost in USD.
        """
        base = (input_tokens * price_in + output_tokens * price_out) / 1_000_000
        cache_write_cost = (cache_creation_tokens * price_in * cache_write_multiplier) / 1_000_000
        cache_read_cost = (cache_read_tokens * price_in * cache_read_multiplier) / 1_000_000
        return base + cache_write_cost + cache_read_cost

    def estimate_precall_cost(
        self,
        input_tokens_est: int,
        price_in: float,
    ) -> float:
        """Estimate cost of a pre-call request.

        Args:
            input_tokens_est: Estimated input tokens for pre-call.
            price_in: Price per 1M input tokens in USD.

        Returns:
            Estimated cost in USD.
        """
        return input_tokens_est * price_in / 1_000_000

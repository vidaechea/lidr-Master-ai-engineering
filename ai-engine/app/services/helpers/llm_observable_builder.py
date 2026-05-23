"""Observable response builder for LLM completions.

Receives pre-calculated cost from LiteLLMRouterService and constructs the response.
"""

import time
from decimal import Decimal
from typing import Any

import structlog

from app.schemas.llm import LLMObservableResponse, LLMUsage

log = structlog.get_logger(__name__)


class LLMObservableResponseBuilder:
    """Builds structured LLM observable responses with latency metrics.

    Cost calculation is delegated to litellm which tracks it automatically.
    """

    def build(
        self,
        model: str,
        usage: Any,
        latency_ms: float,
        content: str | None = None,
        response_id: str | None = None,
        raw_response: Any = None,
        cost_usd: Decimal | None = None,
    ) -> LLMObservableResponse:
        """Construct an observable response wrapper from litellm response.

        Cost is provided by LiteLLMRouterService; this builder simply assembles it.

        Args:
            model: Model name (e.g., 'gpt-4o-mini').
            usage: Usage object with prompt_tokens, completion_tokens attributes.
            latency_ms: Time elapsed in milliseconds.
            content: Response text content (optional for streaming).
            response_id: Provider response ID for tracing.
            raw_response: Raw provider response object from litellm.
            cost_usd: Cost in USD (pre-calculated by LiteLLMRouterService).

        Returns:
            Structured LLMObservableResponse with provided cost.
        """
        prompt_tokens = getattr(usage, "prompt_tokens", 0)
        completion_tokens = getattr(usage, "completion_tokens", 0)
        total_tokens = getattr(usage, "total_tokens", 0)

        # Use provided cost (calculated by LiteLLMRouterService)
        if cost_usd is None:
            cost_usd = Decimal("0")

        return LLMObservableResponse(
            model=model,
            content=content,
            usage=LLMUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            ),
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            response_id=response_id,
            raw_response=raw_response,
        )


    def build_from_timer(
        self,
        model: str,
        usage: Any,
        start_time: float,
        content: str | None = None,
        response_id: str | None = None,
        raw_response: Any = None,
        cost_usd: Decimal | None = None,
    ) -> LLMObservableResponse:
        """Build response, automatically calculating elapsed time from a start time.

        Args:
            model: Model name.
            usage: Usage object.
            start_time: perf_counter() timestamp from before the call.
            content: Response text content.
            response_id: Provider response ID.
            raw_response: Raw provider response object from litellm.
            cost_usd: Cost in USD (pre-calculated by LiteLLMRouterService).

        Returns:
            Structured LLMObservableResponse.
        """
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        return self.build(
            model=model,
            usage=usage,
            latency_ms=elapsed_ms,
            content=content,
            response_id=response_id,
            raw_response=raw_response,
            cost_usd=cost_usd,
        )


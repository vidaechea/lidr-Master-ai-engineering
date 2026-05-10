"""Base LLM Service: Orchestrates LLM provider interactions with specialized responsibilities."""

import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, TypedDict

import structlog
from typing_extensions import Unpack

from app.prompts.loader import format_examples_for_prompt, get_examples, render_estimation_prompt
from app.schemas.estimation import ExampleFormat, DetailLevel, ProjectType
from app.services.helpers.cost_calculator import CostCalculator
from app.services.cache.conversation_state import ConversationState
from app.services.helpers.error_mapper import ErrorMapper, LLMServiceError
from app.services.helpers.prompt_builder import PromptBuilder
from app.services.helpers.token_counter import TokenCounter

log = structlog.get_logger(__name__)

_PRE_CALL_MAX_OUTPUT_TOKENS = 1_024


class _EstimationKwargs(TypedDict, total=False):
    model: str | None
    temperature: float | None
    top_p: float | None
    top_k: int | None
    reasoning_effort: str
    max_output_tokens: int
    continue_conversation: bool
    pre_call: bool
    example_format: ExampleFormat
    num_examples: int
    system_prompt: str
    user_prompt: str


@dataclass
class ModelInfo:
    input_price: float
    output_price: float
    context_window: int
    reasoning: bool
    encoding: str | None = None
    cache_write_price_multiplier: float = 0.0
    cache_read_price_multiplier: float = 0.0
    thinking_api: str | None = None


@dataclass
class ParsedResponse:
    estimation: str
    response_id: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int | None = None
    finish_reason: str = "unknown"
    truncated: bool = False
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    fallback_provider: str | None = None


@dataclass
class CallContext:
    resolved_model: str
    model_info: ModelInfo
    api_params: dict[str, Any]
    pre_call_cost: float
    requirements: str | None
    transcription: str
    estimated_precall_cost_usd: float
    input_tokens_est: int
    is_reasoning: bool
    continue_conversation: bool
    pre_call: bool
    provider: str = "unknown"


class BaseLLMService(ABC):
    """Base service for LLM provider interactions.
    
    Delegates specialized responsibilities to:
    - PromptBuilder: prompt construction and validation
    - CostCalculator: cost estimation
    - ConversationState: conversation history
    - ErrorMapper: exception mapping
    """

    def __init__(self) -> None:
        self._conversation_state = ConversationState()
        self._cost_calculator = CostCalculator()
        self._prompt_builder = PromptBuilder(self._create_token_counter())
        self._error_mapper = ErrorMapper()
        self._stream_partial: ParsedResponse | None = None
        self._last_stream_result: dict[str, Any] | None = None

    def reset(self) -> None:
        """Reset conversation state."""
        self._conversation_state.reset()

    def _create_token_counter(self) -> TokenCounter:
        """Factory method for provider-specific token counter.
        
        Returns:
            Implementation of TokenCounter for this provider.
        """
        raise NotImplementedError("Subclass must implement _create_token_counter")

    def _on_turn_complete(
        self,
        _transcription: str,
        _assistant_content: str,
    ) -> None:
        """Hook for subclasses to override with turn completion logic."""
        pass

    @property
    @abstractmethod
    def _provider_name(self) -> str:
        """Provider name identifier."""
        ...

    @abstractmethod
    def _get_model_info(
        self, model: str | None
    ) -> tuple[str, ModelInfo]:
        """Resolve model name and get pricing/capabilities info."""
        ...

    @abstractmethod
    def _build_api_params(
        self,
        *,
        resolved_model: str,
        system_prompt: str,
        transcription: str,
        model_info: ModelInfo,
        temperature: float | None,
        top_p: float | None,
        top_k: int | None,
        reasoning_effort: str,
        max_output_tokens: int,
        continue_conversation: bool,
    ) -> dict[str, Any]:
        """Build provider-specific API parameters."""
        ...

    @abstractmethod
    async def _call_provider(self, api_params: dict[str, Any]) -> Any:
        """Make the actual API call to the provider."""
        ...

    @abstractmethod
    async def _call_provider_stream(
        self,
        api_params: dict[str, Any],
        *,
        is_reasoning: bool,
    ) -> AsyncIterator[str]:
        """Stream text deltas from the provider API."""
        ...

    @abstractmethod
    def _parse_provider_response(
        self,
        response: Any,
        *,
        is_reasoning: bool,
    ) -> ParsedResponse:
        """Parse provider response into standardized ParsedResponse."""
        ...

    def _validate_sampling_params(
        self,
        temperature: float | None,
        top_p: float | None,
    ) -> None:
        """Validate that sampling parameters are not mutually exclusive."""
        if temperature is not None and top_p is not None:
            raise ValueError(
                "temperature and top_p are mutually exclusive — provide only one."
            )

    async def _run_pre_call(
        self,
        transcription: str,
        *,
        resolved_model: str,
        model_info: ModelInfo,
        temperature: float | None,
        top_p: float | None,
        top_k: int | None,
        reasoning_effort: str,
    ) -> dict[str, Any]:
        """Execute a pre-call to extract requirements."""
        pre_call_system_prompt = self._prompt_builder.build_pre_call_system_prompt(transcription)
        api_params = self._build_api_params(
            resolved_model=resolved_model,
            system_prompt=pre_call_system_prompt,
            transcription=transcription,
            model_info=model_info,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            reasoning_effort=reasoning_effort,
            max_output_tokens=_PRE_CALL_MAX_OUTPUT_TOKENS,
            continue_conversation=False,
        )
        log.debug("running_pre_call", model=resolved_model)
        response = await self._call_provider(api_params)
        partial = self._parse_provider_response(response, is_reasoning=model_info.reasoning)

        cost = self._cost_calculator.compute_cost(
            partial.input_tokens,
            partial.output_tokens,
            model_info.input_price,
            model_info.output_price,
            cache_creation_tokens=partial.cache_creation_tokens,
            cache_read_tokens=partial.cache_read_tokens,
            cache_write_multiplier=model_info.cache_write_price_multiplier,
            cache_read_multiplier=model_info.cache_read_price_multiplier,
        )
        log.info(
            "pre_call_completed",
            model=resolved_model,
            input_tokens=partial.input_tokens,
            output_tokens=partial.output_tokens,
            cost_usd=round(cost, 8),
        )
        return {"requirements": partial.estimation, "cost": cost}

    async def _run_pre_call_stage(
        self,
        transcription: str,
        *,
        resolved_model: str,
        model_info: ModelInfo,
        temperature: float | None,
        top_p: float | None,
        top_k: int | None,
        reasoning_effort: str,
    ) -> tuple[str, float]:
        """Run pre-call stage and return extracted requirements and cost."""
        pre_call_result = await self._run_pre_call(
            transcription,
            resolved_model=resolved_model,
            model_info=model_info,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            reasoning_effort=reasoning_effort,
        )
        return pre_call_result["requirements"], pre_call_result["cost"]

    async def _prepare_call(
        self,
        transcription: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
        reasoning_effort: str = "medium",
        max_output_tokens: int = 2_048,
        continue_conversation: bool = False,
        pre_call: bool = False,
        example_format: ExampleFormat = ExampleFormat.MARKDOWN,
        num_examples: int = 3,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
    ) -> CallContext:
        """Prepare a call context with all necessary parameters and validations."""
        self._validate_sampling_params(temperature, top_p)

        resolved_model, model_info = self._get_model_info(model)
        
        # Estimate pre-call cost
        pre_call_system_prompt = self._prompt_builder.build_pre_call_system_prompt(transcription)
        token_counter = self._create_token_counter()
        precall_input_tokens = token_counter.count_tokens(
            pre_call_system_prompt,
            transcription,
            resolved_model,
        )
        estimated_precall_cost_usd: float = round(
            self._cost_calculator.estimate_precall_cost(
                precall_input_tokens,
                model_info.input_price,
            ),
            8,
        )

        pre_call_cost: float = 0.0
        requirements: str | None = None
        if pre_call:
            requirements, pre_call_cost = await self._run_pre_call_stage(
                transcription,
                resolved_model=resolved_model,
                model_info=model_info,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                reasoning_effort=reasoning_effort,
            )
            transcription = requirements

        # Use pre-rendered prompts if provided, otherwise build them
        if system_prompt is not None and user_prompt is not None:
            computed_system_prompt = system_prompt
            computed_user_prompt = user_prompt
        else:
            computed_system_prompt = self._prompt_builder.build_system_prompt(
                transcription, 
                num_examples=num_examples
            )
            computed_user_prompt = transcription
        
        # Validate context window for both pre-rendered and built prompts
        input_tokens_est = self._prompt_builder.validate_context_window(
            computed_system_prompt,
            computed_user_prompt,
            resolved_model,
            max_output_tokens,
            model_info.context_window,
        )
        user_prompt = computed_user_prompt

        api_params = self._build_api_params(
            resolved_model=resolved_model,
            system_prompt=computed_system_prompt,
            transcription=user_prompt,
            model_info=model_info,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            reasoning_effort=reasoning_effort,
            max_output_tokens=max_output_tokens,
            continue_conversation=continue_conversation,
        )
        return CallContext(
            resolved_model=resolved_model,
            model_info=model_info,
            api_params=api_params,
            pre_call_cost=pre_call_cost,
            requirements=requirements,
            transcription=user_prompt,
            estimated_precall_cost_usd=estimated_precall_cost_usd,
            input_tokens_est=input_tokens_est,
            is_reasoning=model_info.reasoning,
            continue_conversation=continue_conversation,
            pre_call=pre_call,
            provider=self._provider_name,
        )

    def _finalize_turn(
        self,
        partial: ParsedResponse,
        ctx: CallContext,
        *,
        estimation_text: str,
    ) -> dict[str, Any]:
        """Finalize a turn with cost calculation and state management."""
        model_info: ModelInfo = ctx.model_info
        pre_call_cost: float = ctx.pre_call_cost
        actual_input_tokens: int = partial.input_tokens
        actual_output_tokens: int = partial.output_tokens
        cache_creation_tokens: int = partial.cache_creation_tokens
        cache_read_tokens: int = partial.cache_read_tokens
        
        turn_cost = self._cost_calculator.compute_cost(
            actual_input_tokens,
            actual_output_tokens,
            model_info.input_price,
            model_info.output_price,
            cache_creation_tokens=cache_creation_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_multiplier=model_info.cache_write_price_multiplier,
            cache_read_multiplier=model_info.cache_read_price_multiplier,
        )

        continue_conversation: bool = ctx.continue_conversation
        pre_call: bool = ctx.pre_call
        if continue_conversation:
            total_cost = self._conversation_state.record_turn(partial.response_id, turn_cost + pre_call_cost)
            self._on_turn_complete(ctx.transcription, estimation_text)
        else:
            total_cost = turn_cost + pre_call_cost

        return {
            "estimation": estimation_text,
            "model": ctx.resolved_model,
            "input_tokens": actual_input_tokens,
            "output_tokens": actual_output_tokens,
            "reasoning_tokens": partial.reasoning_tokens,
            "cache_creation_tokens": cache_creation_tokens,
            "cache_read_tokens": cache_read_tokens,
            "truncated": partial.truncated,
            "finish_reason": partial.finish_reason,
            "turn_cost_usd": round(turn_cost, 8),
            "total_cost_usd": round(total_cost, 8),
            "response_id": partial.response_id,
            "estimated_input_tokens": ctx.input_tokens_est,
            "estimated_precall_cost_usd": ctx.estimated_precall_cost_usd,
            "requirements": ctx.requirements,
            "pre_call_cost_usd": round(pre_call_cost, 8) if pre_call else None,
        }

    async def _call_and_parse(self, ctx: CallContext) -> ParsedResponse:
        """Call provider and parse response, mapping exceptions appropriately."""
        try:
            response = await self._call_provider(ctx.api_params)
            return self._parse_provider_response(response, is_reasoning=ctx.is_reasoning)
        except LLMServiceError as exc:
            log.error(
                "provider_error",
                error_type=exc.error_type,
                message=exc.message,
                model=ctx.resolved_model,
                provider=ctx.provider,
            )
            raise

    async def estimate(self, transcription: str, **kwargs: Unpack[_EstimationKwargs]) -> dict[str, Any]:
        """Execute a single estimation call."""
        ctx = await self._prepare_call(transcription, **kwargs)
        log.debug(
            "calling_provider",
            model=ctx.resolved_model,
            provider=ctx.provider,
            estimated_input_tokens=ctx.input_tokens_est,
        )
        t0 = time.perf_counter()
        partial = await self._call_and_parse(ctx)
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        result = self._finalize_turn(partial, ctx, estimation_text=partial.estimation)
        log.info(
            "estimation_succeeded",
            model=ctx.resolved_model,
            provider=ctx.provider,
            input_tokens=result["input_tokens"],
            output_tokens=result["output_tokens"],
            reasoning_tokens=result["reasoning_tokens"],
            cache_creation_tokens=result["cache_creation_tokens"],
            cache_read_tokens=result["cache_read_tokens"],
            finish_reason=result["finish_reason"],
            latency_ms=latency_ms,
            turn_cost_usd=result["turn_cost_usd"],
            pre_call_cost_usd=round(ctx.pre_call_cost, 8),
            total_cost_usd=result["total_cost_usd"],
            fallback_provider=partial.fallback_provider,
            continue_conversation=ctx.continue_conversation,
            turn_count=self._conversation_state.turn_count,
        )
        return result

    async def estimate_stream(self, transcription: str, **kwargs: Unpack[_EstimationKwargs]) -> AsyncIterator[str]:
        """Async generator that yields text deltas from the LLM.

        After the iterator is exhausted, ``self._last_stream_result`` holds the
        same metadata dict that ``estimate()`` would have returned.
        """
        ctx = await self._prepare_call(transcription, **kwargs)
        log.debug(
            "calling_provider_stream",
            model=ctx.resolved_model,
            provider=ctx.provider,
            estimated_input_tokens=ctx.input_tokens_est,
        )
        t0 = time.perf_counter()
        full_text_parts: list[str] = []
        try:
            async for delta in self._call_provider_stream(ctx.api_params, is_reasoning=ctx.is_reasoning):
                full_text_parts.append(delta)
                yield delta
        except LLMServiceError as exc:
            log.error(
                "provider_stream_error",
                error_type=exc.error_type,
                message=exc.message,
                model=ctx.resolved_model,
                provider=ctx.provider,
            )
            raise

        latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        partial = self._stream_partial  # set by _call_provider_stream after completion
        result = self._finalize_turn(partial, ctx, estimation_text="".join(full_text_parts))
        log.info(
            "estimation_stream_succeeded",
            model=ctx.resolved_model,
            provider=ctx.provider,
            input_tokens=result["input_tokens"],
            output_tokens=result["output_tokens"],
            finish_reason=result["finish_reason"],
            latency_ms=latency_ms,
            turn_cost_usd=result["turn_cost_usd"],
            total_cost_usd=result["total_cost_usd"],
            fallback_provider=partial.fallback_provider if partial else None,
        )
        self._last_stream_result: dict[str, Any] = result


def _make_active_service() -> "BaseLLMService":
    from app.services.llm.factory import create_llm_service
    return create_llm_service()


_active_service: BaseLLMService | None = None


def _get_active_service() -> "BaseLLMService":
    global _active_service
    if _active_service is None:
        _active_service = _make_active_service()
    return _active_service


async def estimate(transcription: str, **kwargs: Unpack[_EstimationKwargs]) -> dict[str, Any]:
    return await _get_active_service().estimate(transcription, **kwargs)


def estimate_call_tokens(system_prompt: str, user_message: str) -> int:
    service = _get_active_service()
    resolved_model, _ = service._get_model_info(None)
    token_counter = service._create_token_counter()
    return token_counter.count_tokens(system_prompt, user_message, resolved_model)

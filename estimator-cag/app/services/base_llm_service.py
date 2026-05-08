from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any, TypedDict

import structlog
from typing_extensions import Unpack

from app.context.examples import ExampleFormat, format_examples_for_prompt, select_examples

log = structlog.get_logger(__name__)


class _EstimationKwargs(TypedDict, total=False):
    model: str | None
    temperature: float | None
    top_p: float | None
    top_k: int | None
    reasoning_effort: str
    verbosity: str
    max_output_tokens: int
    continue_conversation: bool
    pre_call: bool
    example_format: ExampleFormat
    num_examples: int


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


class LLMServiceError(Exception):
    def __init__(self, error_type: str, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.status_code = status_code

_SYSTEM_PROMPT_TEMPLATE = """\
You are an expert software estimator.
Your task is to analyze meeting transcriptions and produce detailed effort \
estimates for software projects, broken down by task with hours, team \
composition, and timeline.

Use the following examples as reference for the expected format and level \
of detail:

{examples}

Now estimate the new project based on the meeting transcription provided \
by the user.
"""

_PRE_CALL_MAX_OUTPUT_TOKENS = 1_024

_PRE_CALL_SYSTEM_PROMPT = """\
You are an expert business analyst specializing in software requirements.
Your task is to analyze a raw meeting transcription and extract a clean, \
structured list of software requirements.

Filter out:
- Small talk and pleasantries
- Off-topic discussions
- Repetitions and redundant statements
- Administrative details unrelated to the software

Output a clear, structured document with:
- Numbered list of functional requirements
- Any non-functional requirements (performance, security, scalability)
- Constraints and limitations mentioned
- Deadlines or budget information if present

Be concise and precise. Each requirement must be a clear, actionable statement.
"""


class BaseLLMService(ABC):

    def __init__(self) -> None:
        self._last_response_id: str | None = None
        self._turn_count: int = 0
        self._total_cost: float = 0.0
        self._stream_partial: ParsedResponse | None = None
        self._last_stream_result: dict[str, Any] | None = None

    def reset(self) -> None:
        self._last_response_id = None
        self._turn_count = 0
        self._total_cost = 0.0

    def _build_system_prompt(
        self,
        fmt: ExampleFormat = ExampleFormat.MARKDOWN,
        num_examples: int = 3,
    ) -> str:
        examples = select_examples(num_examples)
        return _SYSTEM_PROMPT_TEMPLATE.format(examples=format_examples_for_prompt(examples, fmt))

    def _build_pre_call_system_prompt(self) -> str:
        return _PRE_CALL_SYSTEM_PROMPT

    def _estimate_precall_cost(
        self,
        pre_call_system_prompt: str,
        transcription: str,
        resolved_model: str,
        price_in: float,
    ) -> float:
        input_tokens_est = self._count_tokens(
            pre_call_system_prompt,
            transcription,
            resolved_model,
        )
        return input_tokens_est * price_in / 1_000_000

    def _raise_service_error(
        self,
        exc: Exception,
        mapping: dict[type[Exception], tuple[str, str | Callable[[Exception], str], int]],
    ) -> None:
        for exc_type, (error_type, message, status_code) in mapping.items():
            if isinstance(exc, exc_type):
                resolved_message = message(exc) if callable(message) else message
                raise LLMServiceError(error_type, resolved_message, status_code)
        raise exc

    @staticmethod
    def _build_provider_error_mapping(
        *,
        provider_label: str,
        auth_error_type: type[Exception],
        rate_limit_type: type[Exception],
        bad_request_type: type[Exception],
        connection_type: type[Exception],
        internal_error_type: type[Exception],
    ) -> dict[type[Exception], tuple[str, str | Callable[[Exception], str], int]]:
        return {
            auth_error_type: (
                "authentication_error",
                f"Invalid or missing {provider_label} API key.",
                401,
            ),
            rate_limit_type: (
                "rate_limit_error",
                "Rate limit reached or insufficient credit.",
                429,
            ),
            bad_request_type: (
                "bad_request_error",
                lambda error: f"Invalid request: {error.message}",
                400,
            ),
            connection_type: (
                "connection_error",
                lambda error: f"Connection or server error: {error}",
                503,
            ),
            internal_error_type: (
                "connection_error",
                lambda error: f"Connection or server error: {error}",
                503,
            ),
        }

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
        pre_call_system_prompt = self._build_pre_call_system_prompt()
        api_params = self._build_api_params(
            resolved_model=resolved_model,
            system_prompt=pre_call_system_prompt,
            transcription=transcription,
            model_info=model_info,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            reasoning_effort=reasoning_effort,
            verbosity="low",
            max_output_tokens=_PRE_CALL_MAX_OUTPUT_TOKENS,
            continue_conversation=False,
        )
        log.debug("running_pre_call", model=resolved_model)
        response = await self._call_provider(api_params)
        partial = self._parse_provider_response(response, is_reasoning=model_info.reasoning)

        cost = self._compute_cost(
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

    def _compute_cost(
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
        base = (input_tokens * price_in + output_tokens * price_out) / 1_000_000
        cache_write_cost = (cache_creation_tokens * price_in * cache_write_multiplier) / 1_000_000
        cache_read_cost = (cache_read_tokens * price_in * cache_read_multiplier) / 1_000_000
        return base + cache_write_cost + cache_read_cost

    def _on_turn_complete(
        self,
        _transcription: str,
        _assistant_content: str,
    ) -> None:
        """Hook for subclasses to override with turn completion logic."""
        pass

    @abstractmethod
    def _get_model_info(
        self, model: str | None
    ) -> tuple[str, ModelInfo]: ...

    @abstractmethod
    def _count_tokens(
        self,
        system_prompt: str,
        user_message: str,
        model: str,
    ) -> int: ...

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
        verbosity: str,
        max_output_tokens: int,
        continue_conversation: bool,
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def _call_provider(self, api_params: dict[str, Any]) -> Any: ...

    @abstractmethod
    async def _call_provider_stream(
        self,
        api_params: dict[str, Any],
        *,
        is_reasoning: bool,
    ) -> AsyncIterator[str]: ...

    @abstractmethod
    def _parse_provider_response(
        self,
        response: Any,
        *,
        is_reasoning: bool,
    ) -> ParsedResponse: ...

    def _validate_sampling_params(
        self,
        temperature: float | None,
        top_p: float | None,
    ) -> None:
        if temperature is not None and top_p is not None:
            raise ValueError(
                "temperature and top_p are mutually exclusive — provide only one."
            )

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

    def _build_prompt_and_check_overflow(
        self,
        transcription: str,
        *,
        resolved_model: str,
        context_window: int,
        max_output_tokens: int,
        example_format: ExampleFormat,
        num_examples: int,
    ) -> tuple[str, int]:
        system_prompt = self._build_system_prompt(fmt=example_format, num_examples=num_examples)
        input_tokens_est = self._count_tokens(system_prompt, transcription, resolved_model)
        total_tokens_est = input_tokens_est + max_output_tokens
        if total_tokens_est >= context_window:
            log.warning(
                "context_overflow",
                model=resolved_model,
                estimated_input_tokens=input_tokens_est,
                max_output_tokens=max_output_tokens,
                context_window=context_window,
            )
            raise LLMServiceError(
                "context_overflow",
                (
                    f"Estimated request size ({input_tokens_est} input tokens + "
                    f"{max_output_tokens} max output tokens = {total_tokens_est} total) "
                    f"meets or exceeds the context window for model "
                    f"'{resolved_model}' ({context_window} tokens)."
                ),
                413,
            )
        return system_prompt, input_tokens_est

    async def _prepare_call(
        self,
        transcription: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
        reasoning_effort: str = "medium",
        verbosity: str = "low",
        max_output_tokens: int = 2_048,
        continue_conversation: bool = False,
        pre_call: bool = False,
        example_format: ExampleFormat = ExampleFormat.MARKDOWN,
        num_examples: int = 3,
    ) -> CallContext:
        self._validate_sampling_params(temperature, top_p)

        resolved_model, model_info = self._get_model_info(model)
        pre_call_system_prompt = self._build_pre_call_system_prompt()
        estimated_precall_cost_usd: float = round(
            self._estimate_precall_cost(
                pre_call_system_prompt, transcription, resolved_model, model_info.input_price,
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

        system_prompt, input_tokens_est = self._build_prompt_and_check_overflow(
            transcription,
            resolved_model=resolved_model,
            context_window=model_info.context_window,
            max_output_tokens=max_output_tokens,
            example_format=example_format,
            num_examples=num_examples,
        )
        api_params = self._build_api_params(
            resolved_model=resolved_model,
            system_prompt=system_prompt,
            transcription=transcription,
            model_info=model_info,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            reasoning_effort=reasoning_effort,
            verbosity=verbosity,
            max_output_tokens=max_output_tokens,
            continue_conversation=continue_conversation,
        )
        return CallContext(
            resolved_model=resolved_model,
            model_info=model_info,
            api_params=api_params,
            pre_call_cost=pre_call_cost,
            requirements=requirements,
            transcription=transcription,
            estimated_precall_cost_usd=estimated_precall_cost_usd,
            input_tokens_est=input_tokens_est,
            is_reasoning=model_info.reasoning,
            continue_conversation=continue_conversation,
            pre_call=pre_call,
        )

    def _finalize_turn(
        self,
        partial: ParsedResponse,
        ctx: CallContext,
        *,
        estimation_text: str,
    ) -> dict[str, Any]:
        model_info: ModelInfo = ctx.model_info
        pre_call_cost: float = ctx.pre_call_cost
        actual_input_tokens: int = partial.input_tokens
        actual_output_tokens: int = partial.output_tokens
        cache_creation_tokens: int = partial.cache_creation_tokens
        cache_read_tokens: int = partial.cache_read_tokens
        turn_cost = self._compute_cost(
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
            self._last_response_id = partial.response_id
            self._turn_count += 1
            self._total_cost += turn_cost + pre_call_cost
            total_cost = self._total_cost
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
        try:
            response = await self._call_provider(ctx.api_params)
            return self._parse_provider_response(response, is_reasoning=ctx.is_reasoning)
        except LLMServiceError as exc:
            log.error("provider_error", error_type=exc.error_type, message=exc.message)
            raise

    async def estimate(self, transcription: str, **kwargs: Unpack[_EstimationKwargs]) -> dict[str, Any]:
        ctx = await self._prepare_call(transcription, **kwargs)
        log.debug("calling_provider", model=ctx.resolved_model, estimated_input_tokens=ctx.input_tokens_est)
        partial = await self._call_and_parse(ctx)
        result = self._finalize_turn(partial, ctx, estimation_text=partial.estimation)
        log.info(
            "estimation_succeeded",
            model=ctx.resolved_model,
            input_tokens=result["input_tokens"],
            output_tokens=result["output_tokens"],
            reasoning_tokens=result["reasoning_tokens"],
            cache_creation_tokens=result["cache_creation_tokens"],
            cache_read_tokens=result["cache_read_tokens"],
            turn_cost_usd=result["turn_cost_usd"],
            pre_call_cost_usd=round(ctx.pre_call_cost, 8),
            total_cost_usd=result["total_cost_usd"],
            continue_conversation=ctx.continue_conversation,
            turn_count=self._turn_count,
        )
        return result

    async def estimate_stream(self, transcription: str, **kwargs: Unpack[_EstimationKwargs]) -> AsyncIterator[str]:
        """Async generator that yields text deltas from the LLM.

        After the iterator is exhausted, ``self._last_stream_result`` holds the
        same metadata dict that ``estimate()`` would have returned.
        """
        ctx = await self._prepare_call(transcription, **kwargs)
        log.debug("calling_provider_stream", model=ctx.resolved_model, estimated_input_tokens=ctx.input_tokens_est)
        full_text_parts: list[str] = []
        try:
            async for delta in self._call_provider_stream(ctx.api_params, is_reasoning=ctx.is_reasoning):
                full_text_parts.append(delta)
                yield delta
        except LLMServiceError as exc:
            log.error("provider_stream_error", error_type=exc.error_type, message=exc.message)
            raise

        partial = self._stream_partial  # set by _call_provider_stream after completion
        result = self._finalize_turn(partial, ctx, estimation_text="".join(full_text_parts))
        log.info("estimation_stream_succeeded", model=ctx.resolved_model, input_tokens=result["input_tokens"], output_tokens=result["output_tokens"], turn_cost_usd=result["turn_cost_usd"])
        self._last_stream_result: dict[str, Any] = result


def _make_active_service() -> "BaseLLMService":
    from app.services.factory import create_llm_service
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
    return service._count_tokens(system_prompt, user_message, resolved_model)

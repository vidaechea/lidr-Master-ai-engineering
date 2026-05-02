from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any, Optional

import structlog

from app.context.examples import ESTIMATION_EXAMPLES, ExampleFormat, format_examples_for_prompt

log = structlog.get_logger(__name__)


class LLMServiceError(Exception):
    def __init__(self, type: str, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.type = type
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
        self._last_response_id: Optional[str] = None
        self._turn_count: int = 0
        self._total_cost: float = 0.0

    def reset(self) -> None:
        self._last_response_id = None
        self._turn_count = 0
        self._total_cost = 0.0

    def _build_system_prompt(self) -> str:
        return _SYSTEM_PROMPT_TEMPLATE.format(examples=format_examples_for_prompt(ESTIMATION_EXAMPLES, ExampleFormat.MARKDOWN))

    def _build_pre_call_system_prompt(self) -> str:
        return _PRE_CALL_SYSTEM_PROMPT

    async def _run_pre_call(
        self,
        transcription: str,
        *,
        resolved_model: str,
        model_info: dict[str, Any],
        temperature: Optional[float],
        top_p: Optional[float],
        top_k: Optional[int],
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
        partial = self._parse_provider_response(response, is_reasoning=model_info["reasoning"])

        price_in: float = model_info["input_price"]
        price_out: float = model_info["output_price"]
        cost = self._compute_cost(
            partial["input_tokens"],
            partial["output_tokens"],
            price_in,
            price_out,
            cache_creation_tokens=partial.get("cache_creation_tokens", 0),
            cache_read_tokens=partial.get("cache_read_tokens", 0),
            cache_write_multiplier=model_info.get("cache_write_price_multiplier", 0.0),
            cache_read_multiplier=model_info.get("cache_read_price_multiplier", 0.0),
        )
        log.info(
            "pre_call_completed",
            model=resolved_model,
            input_tokens=partial["input_tokens"],
            output_tokens=partial["output_tokens"],
            cost_usd=round(cost, 8),
        )
        return {"requirements": partial["estimation"], "cost": cost}

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
        self, model: Optional[str]
    ) -> tuple[str, dict[str, Any]]: ...

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
        model_info: dict[str, Any],
        temperature: Optional[float],
        top_p: Optional[float],
        top_k: Optional[int],
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
    ) -> dict[str, Any]: ...

    async def estimate(
        self,
        transcription: str,
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        reasoning_effort: str = "medium",
        verbosity: str = "low",
        max_output_tokens: int = 2_048,
        continue_conversation: bool = False,
        pre_call: bool = False,
    ) -> dict[str, Any]:
        if temperature is not None and top_p is not None:
            raise ValueError(
                "temperature and top_p are mutually exclusive — provide only one."
            )

        resolved_model, model_info = self._get_model_info(model)
        is_reasoning: bool = model_info["reasoning"]
        context_window: int = model_info["context_window"]
        price_in: float = model_info["input_price"]
        price_out: float = model_info["output_price"]

        # Step 1 (optional): pre-call to extract structured requirements
        pre_call_cost: float = 0.0
        requirements: Optional[str] = None
        if pre_call:
            pre_call_result = await self._run_pre_call(
                transcription,
                resolved_model=resolved_model,
                model_info=model_info,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                reasoning_effort=reasoning_effort,
            )
            requirements = pre_call_result["requirements"]
            pre_call_cost = pre_call_result["cost"]
            transcription = requirements

        # Step 2: main estimation call
        system_prompt = self._build_system_prompt()
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

        cost_est = input_tokens_est * price_in / 1_000_000
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
        log.debug(
            "calling_provider",
            model=resolved_model,
            estimated_input_tokens=input_tokens_est,
            estimated_precall_cost_usd=round(cost_est, 8),
        )
        try:
            response = await self._call_provider(api_params)
            partial = self._parse_provider_response(response, is_reasoning=is_reasoning)
        except LLMServiceError as exc:
            log.error(
                "provider_error",
                error_type=exc.type,
                message=exc.message,
            )
            raise

        actual_input_tokens: int = partial["input_tokens"]
        actual_output_tokens: int = partial["output_tokens"]
        cache_creation_tokens: int = partial.get("cache_creation_tokens", 0)
        cache_read_tokens: int = partial.get("cache_read_tokens", 0)
        turn_cost = self._compute_cost(
            actual_input_tokens,
            actual_output_tokens,
            price_in,
            price_out,
            cache_creation_tokens=cache_creation_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_multiplier=model_info.get("cache_write_price_multiplier", 0.0),
            cache_read_multiplier=model_info.get("cache_read_price_multiplier", 0.0),
        )

        if continue_conversation:
            self._last_response_id = partial["response_id"]
            self._turn_count += 1
            self._total_cost += turn_cost + pre_call_cost
            total_cost = self._total_cost
            self._on_turn_complete(transcription, partial["estimation"])
        else:
            total_cost = turn_cost + pre_call_cost

        log.info(
            "estimation_succeeded",
            model=resolved_model,
            input_tokens=actual_input_tokens,
            output_tokens=actual_output_tokens,
            reasoning_tokens=partial.get("reasoning_tokens"),
            cache_creation_tokens=cache_creation_tokens,
            cache_read_tokens=cache_read_tokens,
            turn_cost_usd=round(turn_cost, 8),
            pre_call_cost_usd=round(pre_call_cost, 8),
            total_cost_usd=round(total_cost, 8),
            continue_conversation=continue_conversation,
            turn_count=self._turn_count,
        )

        return {
            "estimation": partial["estimation"],
            "model": resolved_model,
            "input_tokens": actual_input_tokens,
            "output_tokens": actual_output_tokens,
            "reasoning_tokens": partial.get("reasoning_tokens"),
            "cache_creation_tokens": cache_creation_tokens,
            "cache_read_tokens": cache_read_tokens,
            "truncated": partial.get("truncated", False),
            "finish_reason": partial.get("finish_reason", "unknown"),
            "turn_cost_usd": round(turn_cost, 8),
            "total_cost_usd": round(total_cost, 8),
            "response_id": partial["response_id"],
            "estimated_input_tokens": input_tokens_est,
            "estimated_precall_cost_usd": round(cost_est, 8),
            "requirements": requirements,
            "pre_call_cost_usd": round(pre_call_cost, 8) if pre_call else None,
        }

    async def estimate_stream(
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
    ) -> AsyncIterator[str]:
        """Async generator that yields text deltas from the LLM.

        After the iterator is exhausted, ``self._last_stream_result`` holds the
        same metadata dict that ``estimate()`` would have returned.
        """
        if temperature is not None and top_p is not None:
            raise ValueError(
                "temperature and top_p are mutually exclusive — provide only one."
            )

        resolved_model, model_info = self._get_model_info(model)
        is_reasoning: bool = model_info["reasoning"]
        context_window: int = model_info["context_window"]
        price_in: float = model_info["input_price"]
        price_out: float = model_info["output_price"]

        pre_call_cost: float = 0.0
        requirements: str | None = None
        if pre_call:
            pre_call_result = await self._run_pre_call(
                transcription,
                resolved_model=resolved_model,
                model_info=model_info,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                reasoning_effort=reasoning_effort,
            )
            requirements = pre_call_result["requirements"]
            pre_call_cost = pre_call_result["cost"]
            transcription = requirements  # type: ignore[assignment]

        system_prompt = self._build_system_prompt()
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

        cost_est = input_tokens_est * price_in / 1_000_000
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
        log.debug(
            "calling_provider_stream",
            model=resolved_model,
            estimated_input_tokens=input_tokens_est,
        )

        full_text = ""
        try:
            async for delta in self._call_provider_stream(api_params, is_reasoning=is_reasoning):
                full_text += delta
                yield delta
        except LLMServiceError as exc:
            log.error("provider_stream_error", error_type=exc.type, message=exc.message)
            raise

        # --- post-stream: compute costs and store final result ---
        partial = self._stream_partial  # set by _call_provider_stream after completion
        actual_input_tokens: int = partial["input_tokens"]
        actual_output_tokens: int = partial["output_tokens"]
        cache_creation_tokens: int = partial.get("cache_creation_tokens", 0)
        cache_read_tokens: int = partial.get("cache_read_tokens", 0)
        turn_cost = self._compute_cost(
            actual_input_tokens,
            actual_output_tokens,
            price_in,
            price_out,
            cache_creation_tokens=cache_creation_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_multiplier=model_info.get("cache_write_price_multiplier", 0.0),
            cache_read_multiplier=model_info.get("cache_read_price_multiplier", 0.0),
        )

        if continue_conversation:
            self._last_response_id = partial["response_id"]
            self._turn_count += 1
            self._total_cost += turn_cost + pre_call_cost
            total_cost = self._total_cost
            self._on_turn_complete(transcription, full_text)
        else:
            total_cost = turn_cost + pre_call_cost

        log.info(
            "estimation_stream_succeeded",
            model=resolved_model,
            input_tokens=actual_input_tokens,
            output_tokens=actual_output_tokens,
            turn_cost_usd=round(turn_cost, 8),
        )

        self._last_stream_result: dict[str, Any] = {
            "estimation": full_text,
            "model": resolved_model,
            "input_tokens": actual_input_tokens,
            "output_tokens": actual_output_tokens,
            "reasoning_tokens": partial.get("reasoning_tokens"),
            "cache_creation_tokens": cache_creation_tokens,
            "cache_read_tokens": cache_read_tokens,
            "truncated": partial.get("truncated", False),
            "finish_reason": partial.get("finish_reason", "unknown"),
            "turn_cost_usd": round(turn_cost, 8),
            "total_cost_usd": round(total_cost, 8),
            "response_id": partial["response_id"],
            "estimated_input_tokens": input_tokens_est,
            "estimated_precall_cost_usd": round(cost_est, 8),
            "requirements": requirements,
            "pre_call_cost_usd": round(pre_call_cost, 8) if pre_call else None,
        }


def _make_active_service() -> "BaseLLMService":
    from app.services.factory import create_llm_service
    return create_llm_service()


_active_service: BaseLLMService = _make_active_service()


async def estimate(
    transcription: str,
    **kwargs: Any,
) -> dict[str, Any]:
    return await _active_service.estimate(transcription, **kwargs)


def estimate_call_tokens(system_prompt: str, user_message: str) -> int:
    resolved_model, _ = _active_service._get_model_info(None)
    return _active_service._count_tokens(system_prompt, user_message, resolved_model)

from abc import ABC, abstractmethod
from typing import Any, Optional

from app.context.examples import get_examples_context

# --------------------------------------------------------------------------- #
# Shared prompt template  —  CAG: role definition + injected examples
# --------------------------------------------------------------------------- #
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


def _build_system_prompt() -> str:
    """Build the system prompt injecting all CAG context examples."""
    return _SYSTEM_PROMPT_TEMPLATE.format(examples=get_examples_context())


# --------------------------------------------------------------------------- #
# Abstract base class
# --------------------------------------------------------------------------- #
class BaseLLMService(ABC):
    """Abstract base for LLM provider service implementations.

    Subclasses must implement the provider-specific methods:

    - ``_get_model_info``       — resolve and validate the model name.
    - ``_count_tokens``         — token counting with the provider's tokenizer.
    - ``_build_api_params``     — build the provider's API call parameters.
    - ``_call_provider``        — execute the actual API call.
    - ``_parse_provider_response`` — parse the raw response into a standard dict.

    The ``estimate`` template method orchestrates the shared PRE-CALL / CALL /
    POST-CALL pipeline and is inherited as-is by all subclasses.
    """

    def __init__(self) -> None:
        self._last_response_id: Optional[str] = None
        self._turn_count: int = 0
        self._total_cost: float = 0.0

    def reset(self) -> None:
        """Reset multi-turn session state (start a new conversation thread)."""
        self._last_response_id = None
        self._turn_count = 0
        self._total_cost = 0.0

    # ------------------------------------------------------------------ #
    # Concrete shared helpers
    # ------------------------------------------------------------------ #

    def _build_system_prompt(self) -> str:
        """Build the CAG system prompt with injected examples."""
        return _build_system_prompt()

    def _check_context_overflow(
        self,
        input_tokens_est: int,
        context_window: int,
        model: str,
    ) -> Optional[dict[str, Any]]:
        """Return an error dict when estimated tokens exceed the context window."""
        if input_tokens_est > context_window:
            return {
                "error": True,
                "type": "context_overflow",
                "message": (
                    f"Estimated input tokens ({input_tokens_est:,}) exceed the "
                    f"model's context window ({context_window:,}). "
                    "Reduce the prompt or split the transcription."
                ),
                "status_code": 413,
            }
        return None

    def _compute_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        price_in: float,
        price_out: float,
    ) -> float:
        """Compute cost in USD from token counts and per-million-token prices."""
        return (input_tokens * price_in + output_tokens * price_out) / 1_000_000

    # ------------------------------------------------------------------ #
    # Abstract provider-specific methods
    # ------------------------------------------------------------------ #

    def _on_turn_complete(
        self,
        transcription: str,
        assistant_content: str,
    ) -> None:
        """Hook called after each successful multi-turn call. No-op by default."""

    @abstractmethod
    def _get_model_info(
        self, model: Optional[str]
    ) -> tuple[str, dict[str, Any]]:
        """Resolve and validate the model name.

        Returns a ``(resolved_name, model_info_dict)`` tuple, where
        ``model_info_dict`` must contain at minimum:
        ``input_price``, ``output_price``, ``context_window``, ``reasoning``.
        """

    @abstractmethod
    def _count_tokens(
        self,
        system_prompt: str,
        user_message: str,
        model: str,
    ) -> int:
        """Count input tokens using the provider's tokenizer."""

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
    ) -> dict[str, Any]:
        """Build the API call parameters dict for the provider."""

    @abstractmethod
    async def _call_provider(self, api_params: dict[str, Any]) -> Any:
        """Execute the provider API call and return the raw response object."""

    @abstractmethod
    def _parse_provider_response(
        self,
        response: Any,
        *,
        is_reasoning: bool,
    ) -> dict[str, Any]:
        """Parse the raw provider response into a standardised partial dict.

        Returns either:

        - ``{"error": True, "type": ..., "message": ..., ...}`` on failure, or
        - ``{"content": ..., "response_id": ..., "input_tokens": ...,
              "output_tokens": ..., "reasoning_tokens": ...}`` on success.
        """

    # ------------------------------------------------------------------ #
    # Template method: shared estimation pipeline
    # ------------------------------------------------------------------ #

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
    ) -> dict[str, Any]:
        """Generate a software effort estimate from a meeting transcription.

        The call follows a PRE-CALL / CALL / POST-CALL pipeline:
          - PRE-CALL : validates params, forecasts token usage, aborts on overflow.
          - CALL     : delegates to the concrete provider via ``_call_provider``.
          - POST-CALL: reads usage, computes cost, optionally tracks session state.

        Parameters
        ----------
        transcription:
            Raw meeting transcription to estimate.
        model:
            Model identifier. Defaults to the provider's default model.
        temperature:
            Sampling temperature (non-reasoning models only; mutually exclusive
            with ``top_p``).
        top_p:
            Nucleus sampling probability (non-reasoning models only; mutually
            exclusive with ``temperature``).
        reasoning_effort:
            Effort level for reasoning models — ``"low"``, ``"medium"``, or
            ``"high"``.
        max_output_tokens:
            Upper bound on tokens in the model's response.
        continue_conversation:
            When ``True`` the call is chained to the previous response via
            ``previous_response_id`` (multi-turn session, ``store=True``).

        Returns
        -------
        dict with keys:
            ``content``, ``model``, ``input_tokens``, ``output_tokens``,
            ``reasoning_tokens``, ``turn_cost_usd``, ``total_cost_usd``,
            ``response_id``, ``estimated_input_tokens``,
            ``estimated_precall_cost_usd``.

            On error the dict contains ``error=True``, ``type``, ``message``,
            and optionally ``status_code``.
        """
        # ① PRE-CALL — parameter validation & token forecast
        if temperature is not None and top_p is not None:
            raise ValueError(
                "temperature and top_p are mutually exclusive — provide only one."
            )

        resolved_model, model_info = self._get_model_info(model)
        is_reasoning: bool = model_info["reasoning"]
        context_window: int = model_info["context_window"]
        price_in: float = model_info["input_price"]
        price_out: float = model_info["output_price"]

        system_prompt = self._build_system_prompt()
        input_tokens_est = self._count_tokens(system_prompt, transcription, resolved_model)
        total_tokens_est = input_tokens_est + max_output_tokens

        if total_tokens_est >= context_window:
            return {
                "error": True,
                "type": "context_window_overflow",
                "message": (
                    f"Estimated request size ({input_tokens_est} input tokens + "
                    f"{max_output_tokens} max output tokens = {total_tokens_est} total) "
                    f"meets or exceeds the context window for model "
                    f"'{resolved_model}' ({context_window} tokens)."
                ),
                "status_code": 413,
            }

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

        # ② CALL
        response = await self._call_provider(api_params)

        # Provider may return an error dict directly (e.g. caught API exception)
        if isinstance(response, dict) and response.get("error"):
            return response

        # ③ POST-CALL — cost accounting & session state
        partial = self._parse_provider_response(response, is_reasoning=is_reasoning)
        if partial.get("error"):
            return partial

        actual_input_tokens: int = partial["input_tokens"]
        actual_output_tokens: int = partial["output_tokens"]
        turn_cost = self._compute_cost(
            actual_input_tokens, actual_output_tokens, price_in, price_out
        )

        if continue_conversation:
            self._last_response_id = partial["response_id"]
            self._turn_count += 1
            self._total_cost += turn_cost
            total_cost = self._total_cost
            self._on_turn_complete(transcription, partial["content"])
        else:
            total_cost = turn_cost

        return {
            "content": partial["content"],
            "model": resolved_model,
            "input_tokens": actual_input_tokens,
            "output_tokens": actual_output_tokens,
            "reasoning_tokens": partial.get("reasoning_tokens"),
            "truncated": partial.get("truncated", False),
            "turn_cost_usd": round(turn_cost, 8),
            "total_cost_usd": round(total_cost, 8),
            "response_id": partial["response_id"],
            "estimated_input_tokens": input_tokens_est,
            "estimated_precall_cost_usd": round(cost_est, 8),
        }

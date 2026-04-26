from typing import Any, Optional

import tiktoken
from openai import AsyncOpenAI

from app.config import settings
from app.context.examples import get_examples_context

# --------------------------------------------------------------------------- #
# Model registry — pricing in USD per 1 M tokens
# --------------------------------------------------------------------------- #
MODELS: dict[str, dict[str, Any]] = {
    "gpt-4o-mini": {
        "input_price": 0.15,
        "output_price": 0.60,
        "context_window": 128_000,
        "reasoning": False,
    },
    "o4-mini": {
        "input_price": 1.10,
        "output_price": 4.40,
        "context_window": 200_000,
        "reasoning": True,
    },
}

DEFAULT_MODEL: str = settings.llm_model  # "gpt-4o-mini"

# Tokens added by the API per message (role overhead) and response priming
_MSG_OVERHEAD: int = 4
_PRIMING_TOKENS: int = 2

# --------------------------------------------------------------------------- #
# System prompt builder  —  CAG: role definition + injected examples
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
# Pre-call token estimation
# --------------------------------------------------------------------------- #
def estimate_call_tokens(
    system_prompt: str,
    user_message: str,
    model: str = DEFAULT_MODEL,
) -> int:
    """Return the estimated number of input tokens for a system+user call.

    Uses tiktoken to count tokens and adds per-message overhead and priming
    tokens following OpenAI's documented formula.
    """
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")

    tokens = 0
    for text in (system_prompt, user_message):
        tokens += len(encoding.encode(text)) + _MSG_OVERHEAD
    tokens += _PRIMING_TOKENS
    return tokens


# --------------------------------------------------------------------------- #
# Lazy client factory
# --------------------------------------------------------------------------- #
_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


# --------------------------------------------------------------------------- #
# Multi-turn session state  (module-level; one session per process)
# --------------------------------------------------------------------------- #
_last_response_id: Optional[str] = None
_turn_count: int = 0
_total_cost: float = 0.0


# --------------------------------------------------------------------------- #
# Public estimation function
# --------------------------------------------------------------------------- #
async def estimate(
    transcription: str,
    *,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    top_p: Optional[float] = None,
    reasoning_effort: str = "medium",
    max_output_tokens: int = 2_048,
    continue_conversation: bool = False,
) -> dict[str, Any]:
    """Generate a software effort estimate from a meeting transcription.

    The call follows a PRE-CALL / CALL / POST-CALL pipeline:
      - PRE-CALL : validates params, forecasts token usage, aborts on overflow.
      - CALL     : uses the OpenAI Responses API (instructions + input).
      - POST-CALL: reads usage, computes cost, optionally tracks session state.

    Parameters
    ----------
    transcription:
        Raw meeting transcription to estimate.
    model:
        Model identifier.  Defaults to ``settings.llm_model``.
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
    # ------------------------------------------------------------------ #
    # ① PRE-CALL — Token Forecast & Routing
    # ------------------------------------------------------------------ #

    # temperature and top_p are mutually exclusive
    if temperature is not None and top_p is not None:
        raise ValueError(
            "temperature and top_p are mutually exclusive — provide only one."
        )

    # Resolve model and look up registry
    resolved_model = model or DEFAULT_MODEL
    model_info = MODELS.get(resolved_model)
    if model_info is None:
        raise ValueError(
            f"Unknown model '{resolved_model}'. Add it to the MODELS registry."
        )

    is_reasoning: bool = model_info["reasoning"]
    context_window: int = model_info["context_window"]
    price_in: float = model_info["input_price"]
    price_out: float = model_info["output_price"]

    # Build system prompt — CAG: role definition + injected examples
    system_prompt = _build_system_prompt()

    # Token forecast: abort early if context window would be exceeded
    input_tokens_est = estimate_call_tokens(system_prompt, transcription, resolved_model)
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

    cost_est = input_tokens_est * price_in / 1_000_000

    # Build base API params
    api_params: dict[str, Any] = {
        "model": resolved_model,
        "instructions": system_prompt,   # [system] — role + CAG examples
        "input": transcription,          # [user]   — meeting transcription
        "max_output_tokens": max_output_tokens,
        "store": continue_conversation,
    }

    # Parameter routing: reasoning vs. standard models
    if is_reasoning:
        # Reasoning models do not accept temperature or top_p
        api_params["reasoning"] = {"effort": reasoning_effort}
    else:
        if temperature is not None:
            api_params["temperature"] = temperature
        elif top_p is not None:
            api_params["top_p"] = top_p

    # Multi-turn: attach previous_response_id when continuing a session
    global _last_response_id, _turn_count, _total_cost
    if continue_conversation and _last_response_id:
        api_params["previous_response_id"] = _last_response_id

    # ------------------------------------------------------------------ #
    # ② CALL — OpenAI Responses API
    # ------------------------------------------------------------------ #
    client = _get_client()
    response = await client.responses.create(**api_params)

    if response.status != "completed":
        return {
            "error": True,
            "type": response.status,
            "message": f"Response ended with status '{response.status}'.",
        }

    # ------------------------------------------------------------------ #
    # ③ POST-CALL — Usage & Cost Accounting
    # ------------------------------------------------------------------ #
    output_text: str = response.output_text
    usage = response.usage
    actual_input_tokens: int = usage.input_tokens
    actual_output_tokens: int = usage.output_tokens

    # Reasoning tokens are billed inside output_tokens but not visible in
    # output_text — extract them separately for accurate tracking.
    reasoning_tokens: Optional[int] = None
    if is_reasoning and usage.output_tokens_details:
        reasoning_tokens = usage.output_tokens_details.reasoning_tokens

    turn_cost = (
        actual_input_tokens * price_in + actual_output_tokens * price_out
    ) / 1_000_000

    # State mutation only in multi-turn mode
    if continue_conversation:
        _last_response_id = response.id
        _turn_count += 1
        _total_cost += turn_cost
        total_cost = _total_cost
    else:
        total_cost = turn_cost  # stateless: session total == turn cost

    return {
        "content": output_text, # [assistant] response
        "model": resolved_model,
        "input_tokens": actual_input_tokens,
        "output_tokens": actual_output_tokens,
        "reasoning_tokens": reasoning_tokens,
        "turn_cost_usd": round(turn_cost, 8),
        "total_cost_usd": round(total_cost, 8),
        "response_id": response.id,
        "estimated_input_tokens": input_tokens_est,
        "estimated_precall_cost_usd": round(cost_est, 8),
    }

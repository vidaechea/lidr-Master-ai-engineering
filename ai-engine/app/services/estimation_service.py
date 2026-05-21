from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import openai
import structlog

from app.config import MODEL_REGISTRY, settings
from app.guardrails.input import check_input
from app.guardrails.ouput import enforce_scope_response
from app.prompts.loader import render_requirements_extraction_prompt
from app.schemas.estimation import (
    EstimationRequest,
    EstimationResponse,
    EstimationResult,
    ExtractedRequirements,
    UserTier,
)
from app.services.helpers.cost_calculator import CostCalculator
from app.services.helpers.error_mapper import LLMServiceError
from app.services.helpers.output_validator import evaluate_estimation_structure
from app.services.helpers.prompt_builder import PromptBuilder
from app.services.sessions import ConversationHistory, ProjectMetadata

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Moderation client — lazy singleton, None when no OpenAI key is configured
# ---------------------------------------------------------------------------

_moderation_client: openai.OpenAI | None = None


def _get_moderation_client() -> openai.OpenAI | None:
    """Return a cached sync OpenAI client for the Moderation API, or None."""
    if not settings.openai_api_key:
        return None
    global _moderation_client
    if _moderation_client is None:
        _moderation_client = openai.OpenAI(api_key=settings.openai_api_key)
    return _moderation_client


# ---------------------------------------------------------------------------
# Estimation service
# ---------------------------------------------------------------------------

_cost_calculator = CostCalculator()

class EstimationService:
    """Async service that dispatches to the configured LLM provider."""

    async def estimate(
        self, request: EstimationRequest, prompt_version: str = "v1",
        tier: UserTier | None = None,
        project_metadata: ProjectMetadata | None = None,
    ) -> EstimationResponse:
        await asyncio.to_thread(
            check_input,
            request.transcription,
            openai_client=_get_moderation_client(),
        )
        model_name = request.model or settings.llm_model
        model_cfg = MODEL_REGISTRY[model_name]

        builder = PromptBuilder(request, model_cfg, prompt_version, tier=tier, project_metadata=project_metadata)
        builder.validate_context_window()

        estimated_input_tokens = builder.estimated_input_tokens
        estimated_precall_cost_usd = _cost_calculator.estimate_precall_cost(
            estimated_input_tokens, model_cfg.input_price
        )

        requirements: str | None = None
        pre_call_cost_usd: float | None = None

        if request.pre_call:
            req_system, req_user = render_requirements_extraction_prompt(
                request.transcription
            )
            pre_resp = await self._call_provider(
                system_prompt=req_system,
                user_prompt=req_user,
                max_output_tokens=request.max_output_tokens,
            )
            requirements, pre_in_tok, pre_out_tok, *_ = pre_resp
            pre_call_cost_usd = _cost_calculator.compute_cost(
                pre_in_tok, pre_out_tok, model_cfg.input_price, model_cfg.output_price
            )

        main_resp = await self._call_provider(
            system_prompt=builder.system_prompt,
            user_prompt=builder.user_prompt,
            max_output_tokens=request.max_output_tokens,
        )
        estimation_text, input_tokens, output_tokens, finish_reason, response_id = main_resp

        turn_cost_usd = _cost_calculator.compute_cost(
            input_tokens, output_tokens, model_cfg.input_price, model_cfg.output_price
        )
        total_cost_usd = turn_cost_usd + (pre_call_cost_usd or 0.0)

        validation = evaluate_estimation_structure(estimation_text, finish_reason)

        log.info(
            "estimation_completed",
            model=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            turn_cost_usd=turn_cost_usd,
        )

        return EstimationResponse(
            estimation=estimation_text,
            model=model_name,
            response_id=response_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            turn_cost_usd=turn_cost_usd,
            total_cost_usd=total_cost_usd,
            estimated_input_tokens=estimated_input_tokens,
            estimated_precall_cost_usd=estimated_precall_cost_usd,
            requirements=requirements,
            pre_call_cost_usd=pre_call_cost_usd,
            validation=validation,
            prompt_version=prompt_version,
            tier=tier,
        )

    async def estimate_stream(
        self,
        request: EstimationRequest,
        prompt_version: str = "v1",
        tier: UserTier | None = None,
        response_out: list[EstimationResponse] | None = None,
    ) -> AsyncIterator[str]:
        """Stream estimation deltas directly from the LLM.

        When *response_out* is provided, token-usage metadata is captured from
        the final streaming chunk and an :class:`EstimationResponse` is appended
        to the list after the last delta is yielded.
        """
        await asyncio.to_thread(
            check_input,
            request.transcription,
            openai_client=_get_moderation_client(),
        )
        model_name = request.model or settings.llm_model
        model_cfg = MODEL_REGISTRY[model_name]

        builder = PromptBuilder(request, model_cfg, prompt_version, tier=tier)
        builder.validate_context_window()

        log.info(
            "estimation_stream_started",
            model=model_name,
            estimated_input_tokens=builder.estimated_input_tokens,
        )

        from app.services.litellm_service import litellm_router_service

        usage_out: list | None = [] if response_out is not None else None
        async for delta in litellm_router_service.stream(
            messages=[
                {"role": "system", "content": builder.system_prompt},
                {"role": "user", "content": builder.user_prompt},
            ],
            usage_out=usage_out,
            max_tokens=request.max_output_tokens,
        ):
            yield delta

        if response_out is not None and usage_out:
            usage_data = usage_out[0]
            usage = usage_data.get("usage")
            response_id: str = usage_data.get("response_id") or ""
            if usage is not None:
                input_tokens = getattr(usage, "prompt_tokens", 0) or 0
                output_tokens = getattr(usage, "completion_tokens", 0) or 0
                estimated_input_tokens = builder.estimated_input_tokens
                turn_cost_usd = _cost_calculator.compute_cost(
                    input_tokens, output_tokens, model_cfg.input_price, model_cfg.output_price
                )
                response_out.append(EstimationResponse(
                    estimation="",
                    model=model_name,
                    response_id=response_id,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    turn_cost_usd=turn_cost_usd,
                    total_cost_usd=turn_cost_usd,
                    estimated_input_tokens=estimated_input_tokens,
                    estimated_precall_cost_usd=_cost_calculator.estimate_precall_cost(
                        estimated_input_tokens, model_cfg.input_price
                    ),
                    requirements=None,
                    pre_call_cost_usd=None,
                    validation=None,
                    prompt_version=prompt_version,
                ))

    async def _call_provider(
        self,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int,
    ) -> tuple[str, int, int, str, str]:
        """Call the configured provider. Returns (text, input_tokens, output_tokens, finish_reason, response_id)."""
        return await self._call_litellm(system_prompt, user_prompt, max_output_tokens)

    async def _call_litellm(
        self,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int,
    ) -> tuple[str, int, int, str, str]:
        from app.services.litellm_service import litellm_router_service

        response = await litellm_router_service.complete(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_output_tokens,
        )
        return (
            response.choices[0].message.content,
            response.usage.prompt_tokens,
            response.usage.completion_tokens,
            response.choices[0].finish_reason or "stop",
            response.id,
        )

    async def _call_litellm_messages(
        self,
        messages: list[dict[str, str]],
        max_output_tokens: int,
    ) -> tuple[str, int, int, str, str]:
        """Send a pre-built messages list to LiteLLM (used for multi-turn conversations).

        Returns ``(text, input_tokens, output_tokens, finish_reason, response_id)``.
        """
        from app.services.litellm_service import litellm_router_service

        response = await litellm_router_service.complete(
            messages=messages,
            max_tokens=max_output_tokens,
        )
        return (
            response.choices[0].message.content,
            response.usage.prompt_tokens,
            response.usage.completion_tokens,
            response.choices[0].finish_reason or "stop",
            response.id,
        )

    async def estimate_multi_turn(
        self,
        request: EstimationRequest,
        history: ConversationHistory,
        prompt_version: str = "v1",
        project_metadata: ProjectMetadata | None = None,
    ) -> EstimationResponse:
        """Run one estimation turn using the full conversation history.

        Adds the user prompt to *history* before calling the provider and
        appends the assistant response afterwards, so the caller does not need
        to manage history entries manually.

        Args:
            request: The current estimation request (transcript + options).
            history: The session's :class:`~app.services.sessions.ConversationHistory`
                that holds previous turns.  Modified in-place.
            prompt_version: Prompt template version (e.g. ``"v1"``).
            project_metadata: Current session metadata used to refresh the
                system prompt for this turn.

        Returns:
            :class:`~app.schemas.estimation.EstimationResponse` with full cost
            and token metadata.
        """
        await asyncio.to_thread(
            check_input,
            request.transcription,
            openai_client=_get_moderation_client(),
        )
        model_name = request.model or settings.llm_model
        model_cfg = MODEL_REGISTRY[model_name]

        builder = PromptBuilder(request, model_cfg, prompt_version, project_metadata=project_metadata)
        builder.validate_context_window()

        estimated_input_tokens = builder.estimated_input_tokens
        estimated_precall_cost_usd = _cost_calculator.estimate_precall_cost(
            estimated_input_tokens, model_cfg.input_price
        )

        # Register this turn's user message and build the full messages list
        # with the system prompt refreshed from current project_metadata.
        history.add("user", builder.user_prompt)
        messages = history.to_messages_list(system_prompt=builder.system_prompt)

        estimation_text, input_tokens, output_tokens, finish_reason, response_id = (
            await self._call_litellm_messages(messages, request.max_output_tokens)
        )

        # Persist the assistant response in the sliding window.
        history.add("assistant", estimation_text)

        turn_cost_usd = _cost_calculator.compute_cost(
            input_tokens, output_tokens, model_cfg.input_price, model_cfg.output_price
        )

        validation = evaluate_estimation_structure(estimation_text, finish_reason)

        log.info(
            "multi_turn_estimation_completed",
            model=model_name,
            turn=history.turn_count,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            turn_cost_usd=turn_cost_usd,
        )

        return EstimationResponse(
            estimation=estimation_text,
            model=model_name,
            response_id=response_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            turn_cost_usd=turn_cost_usd,
            total_cost_usd=turn_cost_usd,
            estimated_input_tokens=estimated_input_tokens,
            estimated_precall_cost_usd=estimated_precall_cost_usd,
            requirements=None,
            pre_call_cost_usd=None,
            validation=validation,
            prompt_version=prompt_version,
        )

    async def estimate_structured(
        self, request: EstimationRequest, prompt_version: str = "v1", tier: UserTier | None = None
    ) -> tuple[EstimationResult, EstimationResponse]:
        """Use instructor + litellm Router to produce a structured EstimationResult.

        Returns ``(EstimationResult, EstimationResponse)`` so callers have access
        to both the typed breakdown and full cost/token metadata.
        """
        await asyncio.to_thread(
            check_input,
            request.transcription,
            openai_client=_get_moderation_client(),
        )
        from app.services.litellm_service import litellm_router_service

        model_name = request.model or settings.llm_model
        model_cfg = MODEL_REGISTRY[model_name]

        builder = PromptBuilder(request, model_cfg, prompt_version, tier=tier)
        builder.validate_context_window()

        estimated_input_tokens = builder.estimated_input_tokens
        estimated_precall_cost_usd = _cost_calculator.estimate_precall_cost(
            estimated_input_tokens, model_cfg.input_price
        )

        requirements: str | None = None
        extracted_requirements: ExtractedRequirements | None = None
        pre_call_cost_usd: float | None = None

        if request.pre_call:
            req_system, req_user = render_requirements_extraction_prompt(
                request.transcription
            )
            extracted, pre_completion = await litellm_router_service.complete_structured(
                messages=[
                    {"role": "system", "content": req_system},
                    {"role": "user", "content": req_user},
                ],
                response_model=ExtractedRequirements,
                max_tokens=512,
            )
            pre_in_tok = pre_completion.usage.prompt_tokens
            pre_out_tok = pre_completion.usage.completion_tokens
            pre_call_cost_usd = _cost_calculator.compute_cost(
                pre_in_tok, pre_out_tok, model_cfg.input_price, model_cfg.output_price
            )
            extracted_requirements = extracted
            requirements = _format_requirements_text(extracted)

        structured_result, completion = await litellm_router_service.complete_structured(
            messages=[
                {"role": "system", "content": builder.system_prompt},
                {"role": "user", "content": builder.user_prompt},
            ],
            response_model=EstimationResult,
            max_tokens=request.max_output_tokens,
        )

        # --- Output guardrails (mandatory) ---------------------------------
        # 1. Scope filter: rewrite low-confidence results before rendering.
        structured_result = enforce_scope_response(structured_result)
        estimation_markdown = _render_estimation_markdown(structured_result)
        finish_reason = (
            completion.choices[0].finish_reason
            if completion.choices
            else "stop"
        )
        # 2. Structure check: same validator used in the markdown path.
        validation = evaluate_estimation_structure(estimation_markdown, finish_reason)
        # -------------------------------------------------------------------

        input_tokens = completion.usage.prompt_tokens
        output_tokens = completion.usage.completion_tokens
        response_id = completion.id
        turn_cost_usd = _cost_calculator.compute_cost(
            input_tokens, output_tokens, model_cfg.input_price, model_cfg.output_price
        )
        total_cost_usd = turn_cost_usd + (pre_call_cost_usd or 0.0)

        log.info(
            "structured_estimation_completed",
            model=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            turn_cost_usd=turn_cost_usd,
            total_phases=len(structured_result.phases),
            validation_score=validation.score,
            scope_filtered=structured_result.summary.startswith("Out of scope:"),
        )

        return structured_result, EstimationResponse(
            estimation=estimation_markdown,
            model=model_name,
            response_id=response_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            turn_cost_usd=turn_cost_usd,
            total_cost_usd=total_cost_usd,
            estimated_input_tokens=estimated_input_tokens,
            estimated_precall_cost_usd=estimated_precall_cost_usd,
            requirements=requirements,
            pre_call_cost_usd=pre_call_cost_usd,
            validation=validation,
            prompt_version=prompt_version,
            structured_result=structured_result,
            extracted_requirements=extracted_requirements,
        )


# ---------------------------------------------------------------------------
# Helpers for EstimationResult → human-readable text
# ---------------------------------------------------------------------------

def _format_requirements_text(extracted: ExtractedRequirements) -> str:
    lines = [f"[{r.id}] ({r.category.value}) {r.description}" for r in extracted.requirements]
    if extracted.open_questions:
        lines.append("\nOpen questions:")
        lines.extend(f"  - {q}" for q in extracted.open_questions)
    return "\n".join(lines)


def _render_estimation_markdown(result: EstimationResult) -> str:
    """Render a structured EstimationResult as markdown for display."""
    lines = [
        f"## {result.summary}",
        "",
        (
            f"**Confidence:** {result.confidence_pct}%  |  "
            f"**Duration:** {result.total_duration_weeks} weeks  |  "
            f"**Total cost:** {result.total_cost_eur:,} EUR"
        ),
        "",
        "| Phase | Duration (weeks) | Cost (EUR) | Confidence |",
        "|-------|-----------------|------------|------------|",
    ]
    for phase in result.phases:
        lines.append(
            f"| {phase.name} | {phase.duration_weeks} | {phase.cost_eur:,} | {phase.confidence_pct}% |"
        )
    for phase in result.phases:
        if phase.assumptions:
            lines.extend(["", f"**{phase.name}** assumptions:"])
            lines.extend(f"- {a}" for a in phase.assumptions)
    lines.extend(["", f"**Total cost:** {result.total_cost_eur:,} EUR"])
    return "\n".join(lines)


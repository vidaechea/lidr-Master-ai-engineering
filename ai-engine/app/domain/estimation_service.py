from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

import openai
import structlog

from app.config import MODEL_REGISTRY, settings
from app.foundation.guardrails.input import check_input
from app.foundation.guardrails.ouput import enforce_scope_response
from app.foundation.prompts.loader import render_requirements_extraction_prompt
from app.domain.schemas.estimation import (
    EstimationRequest,
    EstimationResponse,
    EstimationResult,
    ExtractedRequirements,
    UserTier,
)
from app.domain.schemas.observation import CacheHitKind, TurnObservedEvent
from app.domain.estimation_renderer import format_requirements_text, render_estimation_markdown
from app.domain.output_validator import evaluate_estimation_structure
from app.foundation.prompts.prompt_builder import PromptBuilder
from app.generation.conversation.sessions import ConversationHistory, ProjectMetadata

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
            requirements, _, _, _finish_reason, _response_id, pre_call_cost_usd = pre_resp

        main_resp = await self._call_provider(
            system_prompt=builder.system_prompt,
            user_prompt=builder.user_prompt,
            max_output_tokens=request.max_output_tokens,
        )
        estimation_text, input_tokens, output_tokens, finish_reason, response_id, turn_cost_usd = main_resp

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
            estimated_input_tokens=builder.estimated_input_tokens,
            estimated_precall_cost_usd=None,
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

        from app.foundation.llm.litellm_service import litellm_router_service

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
            observable_resp = usage_out[0]
            input_tokens = observable_resp.usage.prompt_tokens
            output_tokens = observable_resp.usage.completion_tokens
            response_id = observable_resp.response_id or ""
            turn_cost_usd = float(observable_resp.cost_usd)
            estimated_input_tokens = builder.estimated_input_tokens
            response_out.append(EstimationResponse(
                estimation="",
                model=model_name,
                response_id=response_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                turn_cost_usd=turn_cost_usd,
                total_cost_usd=turn_cost_usd,
                estimated_input_tokens=estimated_input_tokens,
                estimated_precall_cost_usd=None,
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
    ) -> tuple[str, int, int, str, str, float]:
        """Call the configured provider. Returns (text, input_tokens, output_tokens, finish_reason, response_id, cost_usd)."""
        return await self._call_litellm(system_prompt, user_prompt, max_output_tokens)

    async def _call_litellm(
        self,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int,
    ) -> tuple[str, int, int, str, str, float]:
        from app.foundation.llm.litellm_service import litellm_router_service

        observable_resp = await litellm_router_service.complete(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_output_tokens,
        )
        return (
            observable_resp.content or "",
            observable_resp.usage.prompt_tokens,
            observable_resp.usage.completion_tokens,
            "stop",
            observable_resp.response_id or "",
            float(observable_resp.cost_usd),
        )

    async def _call_litellm_messages(
        self,
        messages: list[dict[str, str]],
        max_output_tokens: int,
    ) -> tuple[str, int, int, str, str, float]:
        """Send a pre-built messages list to LiteLLM (used for multi-turn conversations).

        Returns ``(text, input_tokens, output_tokens, finish_reason, response_id, cost_usd)``.
        """
        from app.foundation.llm.litellm_service import litellm_router_service

        observable_resp = await litellm_router_service.complete(
            messages=messages,
            max_tokens=max_output_tokens,
        )
        return (
            observable_resp.content or "",
            observable_resp.usage.prompt_tokens,
            observable_resp.usage.completion_tokens,
            "stop",
            observable_resp.response_id or "",
            float(observable_resp.cost_usd),
        )

    async def estimate_multi_turn(
        self,
        request: EstimationRequest,
        history: ConversationHistory,
        prompt_version: str = "v1",
        project_metadata: ProjectMetadata | None = None,
        session_id: str | None = None,
        enriched_transcript_chars: int | None = None,
        attachments_total_chars: int = 0,
        messages_in_window: int | None = None,
        anchors_count: int = 0,
        summary_chars: int = 0,
        cache_hit_kind: CacheHitKind = CacheHitKind.NONE,
        last_resolved_tier: str | None = None,
    ) -> EstimationResponse:
        """Run one estimation turn using the full conversation history.

        Adds the user prompt to *history* before calling the provider and
        appends the assistant response afterwards, so the caller does not need
        to manage history entries manually.

        Optionally collects context metadata and emits a unified ``turn_observed``
        event at the end of the turn with all relevant metrics.

        Args:
            request: The current estimation request (transcript + options).
            history: The session's :class:`~app.generation.conversation.sessions.ConversationHistory`
                that holds previous turns.  Modified in-place.
            prompt_version: Prompt template version (e.g. ``"v1"``).
            project_metadata: Current session metadata used to refresh the
                system prompt for this turn.
            session_id: Optional session identifier for event observation.
            enriched_transcript_chars: Character count of transcript + attachments.
            attachments_total_chars: Character count from uploaded files.
            messages_in_window: Number of messages in history after compression.
            anchors_count: Number of key information anchors extracted.
            summary_chars: Character count of the conversation summary.
            cache_hit_kind: Type of cache hit achieved (none, exact, semantic).
            last_resolved_tier: User tier resolved by the estimation logic.

        Returns:
            :class:`~app.schemas.estimation.EstimationResponse` with full cost
            and token metadata.
        """
        start_time = time.time()

        await asyncio.to_thread(
            check_input,
            request.transcription,
            openai_client=_get_moderation_client(),
        )
        model_name = request.model or settings.llm_model
        model_cfg = MODEL_REGISTRY[model_name]

        builder = PromptBuilder(request, model_cfg, prompt_version, project_metadata=project_metadata)
        builder.validate_context_window()

        # Register this turn's user message and build the full messages list
        # with the system prompt refreshed from current project_metadata.
        history.add("user", builder.user_prompt)
        messages = history.to_messages_list(system_prompt=builder.system_prompt)

        estimation_text, input_tokens, output_tokens, finish_reason, response_id, turn_cost_usd = (
            await self._call_litellm_messages(messages, request.max_output_tokens)
        )

        # Persist the assistant response in the sliding window.
        history.add("assistant", estimation_text)

        validation = evaluate_estimation_structure(estimation_text, finish_reason)

        # Emit unified turn observation event if session_id is provided
        if session_id is not None:
            elapsed_ms = (time.time() - start_time) * 1000
            turn_index = history.turn_count

            # Use provided values or compute from defaults
            transcript_chars = enriched_transcript_chars or len(request.transcription)
            msg_count = messages_in_window or len(history.messages())

            turn_event = TurnObservedEvent(
                turn_index=turn_index,
                session_id=session_id,
                enriched_transcript_chars=transcript_chars,
                attachments_total_chars=attachments_total_chars,
                messages_in_window=msg_count,
                anchors_count=anchors_count,
                summary_chars=summary_chars,
                tokens_in=input_tokens,
                tokens_out=output_tokens,
                cost_usd=turn_cost_usd,
                latency_ms=elapsed_ms,
                cache_hit_kind=cache_hit_kind,
                last_resolved_tier=last_resolved_tier,
                model=model_name,
                response_id=response_id,
            )
            log.info("turn_observed", **turn_event.model_dump())

        return EstimationResponse(
            estimation=estimation_text,
            model=model_name,
            response_id=response_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            turn_cost_usd=turn_cost_usd,
            total_cost_usd=turn_cost_usd,
            estimated_input_tokens=builder.estimated_input_tokens,
            estimated_precall_cost_usd=None,
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
        from app.foundation.llm.litellm_service import litellm_router_service

        model_name = request.model or settings.llm_model
        model_cfg = MODEL_REGISTRY[model_name]

        builder = PromptBuilder(request, model_cfg, prompt_version, tier=tier)
        builder.validate_context_window()

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
            pre_call_cost_usd = float(pre_completion.cost_usd)
            extracted_requirements = extracted
            requirements = format_requirements_text(extracted)

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
        estimation_markdown = render_estimation_markdown(structured_result)
        finish_reason = "stop"  # Observable response doesn't track finish_reason
        # 2. Structure check: same validator used in the markdown path.
        validation = evaluate_estimation_structure(estimation_markdown, finish_reason)
        # -------------------------------------------------------------------

        turn_cost_usd = float(completion.cost_usd)
        total_cost_usd = turn_cost_usd + (pre_call_cost_usd or 0.0)

        log.info(
            "structured_estimation_completed",
            model=model_name,
            input_tokens=completion.usage.prompt_tokens,
            output_tokens=completion.usage.completion_tokens,
            turn_cost_usd=turn_cost_usd,
            total_phases=len(structured_result.phases),
            validation_score=validation.score,
            scope_filtered=structured_result.summary.startswith("Out of scope:"),
        )

        return structured_result, EstimationResponse(
            estimation=estimation_markdown,
            model=model_name,
            response_id=completion.response_id or "",
            input_tokens=completion.usage.prompt_tokens,
            output_tokens=completion.usage.completion_tokens,
            turn_cost_usd=turn_cost_usd,
            total_cost_usd=total_cost_usd,
            estimated_input_tokens=builder.estimated_input_tokens,
            estimated_precall_cost_usd=None,
            requirements=requirements,
            pre_call_cost_usd=pre_call_cost_usd,
            validation=validation,
            prompt_version=prompt_version,
            structured_result=structured_result,
            extracted_requirements=extracted_requirements,
        )





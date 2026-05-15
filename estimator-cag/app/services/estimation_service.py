from __future__ import annotations

from collections.abc import AsyncIterator

import structlog

from app.config import MODEL_REGISTRY, settings
from app.prompts.loader import render_requirements_extraction_prompt
from app.schemas.estimation import (
    EstimationRequest,
    EstimationResponse,
    EstimationResult,
    ExtractedRequirements,
)
from app.services.helpers.cost_calculator import CostCalculator
from app.services.helpers.error_mapper import LLMServiceError
from app.services.helpers.output_validator import evaluate_estimation_structure
from app.services.helpers.prompt_builder import PromptBuilder

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Estimation service
# ---------------------------------------------------------------------------

_cost_calculator = CostCalculator()

class EstimationService:
    """Async service that dispatches to the configured LLM provider."""

    async def estimate(
        self, request: EstimationRequest, prompt_version: str = "v1"
    ) -> EstimationResponse:
        model_name = request.model or settings.llm_model
        model_cfg = MODEL_REGISTRY[model_name]

        builder = PromptBuilder(request, model_cfg, prompt_version)
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

        validation = (
            evaluate_estimation_structure(estimation_text, finish_reason)
            if request.evaluate
            else None
        )

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
        )

    async def estimate_stream(
        self,
        request: EstimationRequest,
        prompt_version: str = "v1",
        response_out: list[EstimationResponse] | None = None,
    ) -> AsyncIterator[str]:
        """Stream estimation deltas directly from the LLM.

        When *response_out* is provided, token-usage metadata is captured from
        the final streaming chunk and an :class:`EstimationResponse` is appended
        to the list after the last delta is yielded.
        """
        model_name = request.model or settings.llm_model
        model_cfg = MODEL_REGISTRY[model_name]

        builder = PromptBuilder(request, model_cfg, prompt_version)
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

    async def estimate_structured(
        self, request: EstimationRequest, prompt_version: str = "v1"
    ) -> tuple[EstimationResult, EstimationResponse]:
        """Use instructor + litellm Router to produce a structured EstimationResult.

        Returns ``(EstimationResult, EstimationResponse)`` so callers have access
        to both the typed breakdown and full cost/token metadata.
        """
        from app.services.litellm_service import litellm_router_service

        model_name = request.model or settings.llm_model
        model_cfg = MODEL_REGISTRY[model_name]

        builder = PromptBuilder(request, model_cfg, prompt_version)
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
        )

        return structured_result, EstimationResponse(
            estimation=_render_estimation_markdown(structured_result),
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
            validation=None,
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


"""Actor-Critic-Boss estimation service.

Three roles with structurally distinct objectives:
  - Actor    : generates the candidate estimate (existing prompt pipeline, unchanged).
  - Critic   : audits the candidate against explicit criteria; returns structured
               CriticFeedback with typed issues (category, severity, affected_field).
  - Boss     : makes the governance decision (accept / iterate / synthesize) with an
               explicit iteration budget cap to control cost and latency.

Anti-patterns avoided:
  - Prompts are structurally distinct — actor optimises for generation, critic for fault
    detection, boss for process governance.
  - Critic output is always structured (CriticFeedback Pydantic schema), never free text.
  - The boss always operates with a hard budget; when exhausted it synthesises the best
    available result rather than iterating indefinitely.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import structlog

from app.config import settings
from app.guardrails.input import check_input
from app.prompts.loader import render_boss_prompt, render_critic_prompt, render_estimation_prompt
from app.schemas.estimation import (
    ActorCriticBossRequest,
    ActorCriticBossResponse,
    BossAction,
    BossDecision,
    CriticFeedback,
    IterationTrace,
    UserTier,
)
from app.services.estimation_service import _get_moderation_client
from app.services.helpers.output_validator import evaluate_estimation_structure
from app.services.sessions import ProjectMetadata

log = structlog.get_logger(__name__)


@dataclass
class _LoopState:
    """Mutable accumulator passed through each iteration of the ACB loop."""

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    traces: list[IterationTrace] = field(default_factory=list)
    candidate_text: str = ""
    final_text: str = ""
    final_decision: BossDecision | None = None
    last_critic_feedback: CriticFeedback | None = None
    iteration_instructions: str | None = None
    first_actor_response_id: str = ""

    def add_tokens(self, in_tok: int, out_tok: int, cost: float) -> None:
        self.total_input_tokens += in_tok
        self.total_output_tokens += out_tok
        self.total_cost_usd += cost


class ActorCriticBossService:
    """Runs the actor → critic → boss loop with an iteration budget cap."""

    async def estimate(
        self,
        request: ActorCriticBossRequest,
        prompt_version: str = "v1",
        tier: UserTier | None = None,
        project_metadata: ProjectMetadata | None = None,
    ) -> ActorCriticBossResponse:
        # ── Guardrails run ONCE at the top of the pipeline ────────────────────
        await asyncio.to_thread(
            check_input,
            request.transcription,
            openai_client=_get_moderation_client(),
        )

        from app.services.litellm_service import litellm_router_service

        model_name = request.model or settings.llm_model
        base_sys, base_user = render_estimation_prompt(
            request, version=prompt_version, tier=tier, project_metadata=project_metadata
        )
        estimated_input_tokens = (len(base_sys) + len(base_user)) // 4

        state = _LoopState()

        for iteration in range(request.max_iterations + 1):
            await self._run_actor(
                state, request, prompt_version, tier, project_metadata,
                litellm_router_service, iteration,
            )
            await self._run_critic(
                state, request, project_metadata, litellm_router_service,
            )
            boss_decision = await self._run_boss(
                state, request, project_metadata, litellm_router_service, iteration,
            )

            log.info(
                "acb_iteration_completed",
                iteration=iteration,
                max_iterations=request.max_iterations,
                action=boss_decision.action,
                critic_approved=state.traces[-1].critic_feedback.approved,
                issues_count=len(state.traces[-1].critic_feedback.issues),
            )

            done, fallback = self._handle_boss_decision(state, boss_decision, iteration, request)
            if done or fallback:
                break

        if not state.final_text:
            state.final_text = state.candidate_text

        validation = evaluate_estimation_structure(state.final_text, "stop")
        log.info(
            "acb_pipeline_completed",
            model=model_name,
            total_iterations=len(state.traces),
            total_input_tokens=state.total_input_tokens,
            total_output_tokens=state.total_output_tokens,
            total_cost_usd=round(state.total_cost_usd, 6),
            final_action=state.final_decision.action if state.final_decision else None,
        )

        return ActorCriticBossResponse(
            estimation=state.final_text,
            model=model_name,
            response_id=state.first_actor_response_id,
            input_tokens=state.total_input_tokens,
            output_tokens=state.total_output_tokens,
            turn_cost_usd=state.total_cost_usd,
            total_cost_usd=state.total_cost_usd,
            estimated_input_tokens=estimated_input_tokens,
            estimated_precall_cost_usd=None,
            requirements=None,
            pre_call_cost_usd=None,
            validation=validation,
            prompt_version=prompt_version,
            tier=tier,
            iterations=state.traces,
            final_decision=state.final_decision,
            acb_total_input_tokens=state.total_input_tokens,
            acb_total_output_tokens=state.total_output_tokens,
        )

    # ── Private role helpers ───────────────────────────────────────────────────

    async def _run_actor(
        self, state: _LoopState, request: ActorCriticBossRequest,
        prompt_version: str, tier: UserTier | None,
        project_metadata: ProjectMetadata | None, litellm_service, iteration: int,
    ) -> None:
        sys_prompt, user_prompt = render_estimation_prompt(
            request, version=prompt_version, tier=tier, project_metadata=project_metadata
        )
        if iteration > 0 and state.iteration_instructions and state.candidate_text:
            critic_issues_text = ""
            if state.last_critic_feedback and state.last_critic_feedback.issues:
                issue_lines = [
                    (
                        f"- [{issue.severity.value.upper()}] {issue.category.value} "
                        f"({issue.affected_field}): {issue.description}"
                    )
                    for issue in state.last_critic_feedback.issues
                ]
                critic_issues_text = "\n".join(issue_lines)
            user_prompt += (
                f"\n\n---\n**Correction instructions (iteration {iteration}):**\n"
                f"{state.iteration_instructions}\n\n"
                "**Critic issues to resolve (mandatory):**\n"
                f"{critic_issues_text or '- No explicit issues provided by critic.'}\n\n"
                "Prioritize critical and major issues first and ensure the revised estimate "
                "remains internally consistent (totals, phases, and risks).\n\n"
                f"**Previous estimate to revise:**\n{state.candidate_text}\n---"
            )
        observable_resp = await litellm_service.complete(
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=request.max_output_tokens,
        )
        state.candidate_text = observable_resp.content or ""
        if iteration == 0:
            state.first_actor_response_id = observable_resp.response_id or ""
        state.add_tokens(
            observable_resp.usage.prompt_tokens,
            observable_resp.usage.completion_tokens,
            float(observable_resp.cost_usd),
        )

    async def _run_critic(
        self, state: _LoopState, request: ActorCriticBossRequest,
        project_metadata: ProjectMetadata | None, litellm_service,
    ) -> CriticFeedback:
        critic_sys, critic_user = render_critic_prompt(
            candidate_estimate=state.candidate_text,
            request=request,
            project_metadata=project_metadata,
        )
        critic_feedback, observable_resp = await litellm_service.complete_structured(
            messages=[
                {"role": "system", "content": critic_sys},
                {"role": "user", "content": critic_user},
            ],
            response_model=CriticFeedback,
            max_tokens=1024,
        )
        state.add_tokens(
            observable_resp.usage.prompt_tokens,
            observable_resp.usage.completion_tokens,
            float(observable_resp.cost_usd),
        )
        state.last_critic_feedback = critic_feedback
        return critic_feedback

    async def _run_boss(
        self, state: _LoopState, request: ActorCriticBossRequest,
        project_metadata: ProjectMetadata | None, litellm_service, iteration: int,
    ) -> BossDecision:
        critic_feedback = state.last_critic_feedback
        if critic_feedback is None:
            raise RuntimeError("Boss cannot run before critic feedback is available")
        boss_sys, boss_user = render_boss_prompt(
            candidate_estimate=state.candidate_text,
            critic_feedback=critic_feedback,
            iteration=iteration,
            max_iterations=request.max_iterations,
            project_metadata=project_metadata,
        )
        boss_decision, observable_resp = await litellm_service.complete_structured(
            messages=[
                {"role": "system", "content": boss_sys},
                {"role": "user", "content": boss_user},
            ],
            response_model=BossDecision,
            max_tokens=request.max_output_tokens,
        )
        state.add_tokens(
            observable_resp.usage.prompt_tokens,
            observable_resp.usage.completion_tokens,
            float(observable_resp.cost_usd),
        )
        state.traces.append(
            IterationTrace(
                iteration=iteration,
                candidate_estimate=state.candidate_text,
                critic_feedback=critic_feedback,
                boss_decision=boss_decision,
            )
        )
        state.final_decision = boss_decision
        return boss_decision

    @staticmethod
    def _handle_boss_decision(
        state: _LoopState,
        boss_decision: BossDecision,
        iteration: int,
        request: ActorCriticBossRequest,
    ) -> tuple[bool, bool]:
        """Apply boss decision to state. Returns (done, budget_exhausted_fallback)."""
        if boss_decision.action == BossAction.ACCEPT:
            state.final_text = state.candidate_text
            return True, False

        if boss_decision.action == BossAction.SYNTHESIZE:
            state.final_text = boss_decision.synthesized_estimate or state.candidate_text
            return True, False

        # ITERATE
        if iteration >= request.max_iterations:
            log.warning(
                "acb_budget_exhausted_on_iterate",
                iteration=iteration,
                max_iterations=request.max_iterations,
            )
            state.final_text = state.candidate_text
            return False, True

        state.iteration_instructions = boss_decision.iteration_instructions
        return False, False


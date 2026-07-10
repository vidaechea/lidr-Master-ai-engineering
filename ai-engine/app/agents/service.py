from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

import structlog
from openai import OpenAI

from app.agents.schemas import AgentTraceStep, AgenticEstimate, AgenticEstimationResponse
from app.agents.tools import build_agent_tools, calculate_estimate, search_budgets
from app.config import settings
from app.dependencies import get_openai_client, get_semantic_retriever
from app.domain.estimation_service import _get_moderation_client
from app.domain.schemas.estimation import EstimationRequest
from app.foundation.guardrails.input import check_input
from app.generation.rag.retriever_service import SemanticRetriever

log = structlog.get_logger(__name__)


@dataclass
class _AgentRunState:
    trace: list[AgentTraceStep] = field(default_factory=list)
    structured_result: AgenticEstimate | None = None
    last_response_text: str = ""
    reasoning_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class AgenticEstimationService:
    def __init__(
        self,
        *,
        client: OpenAI | None = None,
        retriever: SemanticRetriever | None = None,
        model_name: str = "gpt-5",
        reasoning_effort: str = "medium",
        max_turns: int = 12,
    ) -> None:
        self._client = client or get_openai_client()
        self._retriever = retriever or get_semantic_retriever()
        self._model_name = model_name
        self._reasoning_effort = reasoning_effort
        self._max_turns = max_turns

    async def estimate(
        self,
        request: EstimationRequest,
        *,
        prompt_version: str = "v1",
    ) -> AgenticEstimationResponse:
        await asyncio.to_thread(
            check_input,
            request.transcription,
            openai_client=_get_moderation_client(),
        )

        state, response = await self._run_loop(request)
        final_text = state.last_response_text or self._render_final_text(state.structured_result)

        log.info(
            "agentic_estimation_completed",
            model=request.model or self._model_name,
            prompt_version=prompt_version,
            steps=len(state.trace),
            input_tokens=state.input_tokens,
            output_tokens=state.output_tokens,
        )

        return AgenticEstimationResponse(
            estimation=final_text,
            structured_result=state.structured_result,
            trace=state.trace,
            model=request.model or self._model_name,
            response_id=getattr(response, "id", ""),
            input_tokens=state.input_tokens,
            output_tokens=state.output_tokens,
            reasoning_tokens=state.reasoning_tokens,
            prompt_version=prompt_version,
            reasoning_effort=self._reasoning_effort,  # type: ignore[arg-type]
        )

    async def _run_loop(self, request: EstimationRequest) -> tuple[_AgentRunState, object]:
        state = _AgentRunState()
        input_items: list[dict[str, object]] = [
            {
                "role": "user",
                "content": request.transcription,
            }
        ]
        response: object | None = None

        for _ in range(1, self._max_turns + 1):
            response = self._create_response(request, input_items, response)
            self._accumulate_usage(state, response)

            function_calls = self._function_calls(response)
            if not function_calls:
                state.last_response_text = self._extract_output_text(response)
                break

            reasoning_summary = self._extract_reasoning_summary(response)
            input_items = await self._execute_function_calls(
                state=state,
                function_calls=function_calls,
                reasoning_summary=reasoning_summary,
            )

        if response is None:
            raise RuntimeError("Agent run did not start")
        if state.structured_result is None:
            raise RuntimeError("The agent finished without producing a structured estimate")
        return state, response

    def _create_response(
        self,
        request: EstimationRequest,
        input_items: list[dict[str, object]],
        previous_response: object | None,
    ) -> object:
        common_kwargs = {
            "model": request.model or self._model_name,
            "instructions": self._system_prompt(),
            "input": input_items,
            "tools": build_agent_tools(),
            "reasoning": {"effort": self._reasoning_effort, "summary": "auto"},
            "max_output_tokens": request.max_output_tokens,
        }
        if previous_response is None:
            return self._client.responses.create(**common_kwargs)
        return self._client.responses.create(previous_response_id=getattr(previous_response, "id"), **common_kwargs)

    @staticmethod
    def _function_calls(response: object) -> list[object]:
        return [item for item in getattr(response, "output", []) if getattr(item, "type", None) == "function_call"]

    async def _execute_function_calls(
        self,
        *,
        state: _AgentRunState,
        function_calls: list[object],
        reasoning_summary: str,
    ) -> list[dict[str, object]]:
        next_input_items: list[dict[str, object]] = []
        for function_call in function_calls:
            arguments = json.loads(getattr(function_call, "arguments", "{}") or "{}")
            action = self._format_action(function_call.name, arguments)
            output_text, observation = await self._run_single_tool(function_call.name, arguments)

            if function_call.name == "calculate_estimate":
                state.structured_result = calculate_estimate(components=list(arguments["components"]))

            state.trace.append(
                AgentTraceStep(
                    step=len(state.trace) + 1,
                    reasoning=reasoning_summary or self._fallback_reasoning(function_call.name, arguments),
                    action=action,
                    observation=observation,
                )
            )
            next_input_items.append(
                {
                    "type": "function_call_output",
                    "call_id": function_call.call_id,
                    "output": output_text,
                }
            )
        return next_input_items

    async def _run_single_tool(self, name: str, arguments: dict[str, object]) -> tuple[str, str]:
        if name == "search_budgets":
            result = await search_budgets(
                self._retriever,
                query=str(arguments["query"]),
                filters=arguments.get("filters"),
            )
            return json.dumps(result, ensure_ascii=False), self._summarize_search_results(result)

        if name == "calculate_estimate":
            result = calculate_estimate(components=list(arguments["components"]))
            return result.model_dump_json(), self._summarize_calculation(result)

        raise RuntimeError(f"Unknown agent tool: {name}")

    @staticmethod
    def _accumulate_usage(state: _AgentRunState, response: object) -> None:
        state.input_tokens += AgenticEstimationService._safe_usage_int(response, "input_tokens")
        state.output_tokens += AgenticEstimationService._safe_usage_int(response, "output_tokens")
        state.reasoning_tokens += AgenticEstimationService._safe_reasoning_tokens(response)

    def _system_prompt(self) -> str:
        return (
            "You are an estimation agent that works step by step. "
            "Your job is to decompose the meeting transcript into distinct components, "
            "search historical budgets separately for each component when needed, "
            "and then call calculate_estimate to consolidate the component estimates. "
            "Do not invent reference amounts. Use search_budgets whenever a component lacks enough evidence. "
            "If the transcript mentions multiple domains such as backend, ERP, or mobile, treat them as separate components. "
            "After the final calculation, provide a concise summary of the estimate."
        )

    @staticmethod
    def _extract_reasoning_summary(response) -> str:
        summaries: list[str] = []
        for item in getattr(response, "output", []):
            if getattr(item, "type", None) != "reasoning":
                continue
            for summary_item in getattr(item, "summary", []) or []:
                text = getattr(summary_item, "text", None)
                if text:
                    summaries.append(text.strip())
        return "\n\n".join(summaries)

    @staticmethod
    def _extract_output_text(response) -> str:
        output_text = getattr(response, "output_text", "") or ""
        if output_text:
            return output_text.strip()

        texts: list[str] = []
        for item in getattr(response, "output", []):
            if getattr(item, "type", None) != "message":
                continue
            for content_item in getattr(item, "content", []) or []:
                if getattr(content_item, "type", None) == "output_text":
                    text = getattr(content_item, "text", None)
                    if text:
                        texts.append(text.strip())
        return "\n".join(texts).strip()

    @staticmethod
    def _format_action(name: str, arguments: dict[str, object]) -> str:
        return f"{name}({json.dumps(arguments, ensure_ascii=False, sort_keys=True)})"

    @staticmethod
    def _summarize_search_results(results: list[dict[str, object]]) -> str:
        if not results:
            return "No historical matches were found."

        items = []
        for result in results[:3]:
            amount = result.get("amount")
            component_name = result.get("component_name")
            budget_id = result.get("budget_id")
            year = result.get("year")
            items.append(f"{component_name}={amount} ({budget_id or 'unknown budget'}, {year or 'unknown year'})")
        suffix = "" if len(results) <= 3 else f" and {len(results) - 3} more"
        return f"{len(results)} matches: {', '.join(items)}{suffix}."

    @staticmethod
    def _summarize_calculation(result: AgenticEstimate) -> str:
        breakdown = ", ".join(
            f"{component.name}={component.estimated_amount}"
            for component in result.components
        )
        return f"Calculated {len(result.components)} components ({breakdown}); total={result.total_amount}."

    @staticmethod
    def _fallback_reasoning(name: str, arguments: dict[str, object]) -> str:
        if name == "search_budgets":
            return f"The agent needs historical references for {arguments.get('query', 'a component')} before estimating."
        if name == "calculate_estimate":
            return "The agent has enough reference amounts to consolidate the estimate."
        return "The agent selected a tool call to continue the estimation."

    @staticmethod
    def _render_final_text(result: AgenticEstimate) -> str:
        lines = ["# Agentic estimate", ""]
        for component in result.components:
            lines.append(
                f"- {component.name}: {component.estimated_amount} {result.unit} "
                f"from {component.reference_count} references"
            )
        lines.append("")
        lines.append(f"Total: {result.total_amount} {result.unit}")
        return "\n".join(lines)

    @staticmethod
    def _safe_usage_int(response, field_name: str) -> int:
        usage = getattr(response, "usage", None)
        if usage is None:
            return 0
        value = getattr(usage, field_name, 0)
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _safe_reasoning_tokens(response) -> int:
        usage = getattr(response, "usage", None)
        details = getattr(usage, "output_tokens_details", None) if usage is not None else None
        value = getattr(details, "reasoning_tokens", 0) if details is not None else 0
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

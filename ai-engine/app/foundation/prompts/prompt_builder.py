from __future__ import annotations

from app.config import ModelConfig
from app.foundation.prompts.loader import render_estimation_prompt
from app.domain.schemas.estimation import EstimationRequest, UserTier
from app.foundation.llm.error_mapper import LLMServiceError
from app.generation.conversation.sessions import ProjectMetadata


class PromptBuilder:
    """Builds and validates prompts for an estimation request."""

    def __init__(
        self,
        request: EstimationRequest,
        model_cfg: ModelConfig,
        prompt_version: str = "v1",
        tier: UserTier | None = None,
        project_metadata: ProjectMetadata | None = None,
    ) -> None:
        self._request = request
        self._model_cfg = model_cfg
        self._system_prompt, self._user_prompt = render_estimation_prompt(
            request, version=prompt_version, tier=tier, project_metadata=project_metadata
        )

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    @property
    def user_prompt(self) -> str:
        return self._user_prompt

    @property
    def estimated_input_tokens(self) -> int:
        """Rough estimate: 1 token ≈ 4 characters."""
        return (len(self._system_prompt) + len(self._user_prompt)) // 4

    def validate_context_window(self) -> None:
        """Raise LLMServiceError(413) if the estimated prompt exceeds the context window."""
        estimated = self.estimated_input_tokens
        limit = self._model_cfg.context_window
        if estimated > limit:
            raise LLMServiceError(
                "context_overflow",
                f"Estimated request size ({estimated} tokens) exceeds the model context window ({limit} tokens).",
                413,
            )



from __future__ import annotations

from app.config import ModelConfig
from app.prompts.loader import render_estimation_prompt
from app.schemas.estimation import EstimationRequest
from app.services.helpers.error_mapper import LLMServiceError


class PromptBuilder:
    """Builds and validates prompts for an estimation request."""

    def __init__(
        self,
        request: EstimationRequest,
        model_cfg: ModelConfig,
        prompt_version: str = "v1",
    ) -> None:
        self._request = request
        self._model_cfg = model_cfg
        self._system_prompt, self._user_prompt = render_estimation_prompt(
            request, version=prompt_version
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

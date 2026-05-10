"""PromptBuilder: Builds prompts and validates context window constraints."""

import structlog

from app.prompts.loader import (
    render_requirements_extraction_prompt,
)
from app.schemas.estimation import ExampleFormat
from app.services.helpers.error_mapper import LLMServiceError
from app.services.helpers.token_counter import TokenCounter

log = structlog.get_logger(__name__)


class PromptBuilder:
    """Handles system/user prompt construction and validation.
    
    Responsible for:
    - Building prompts from templates
    - Validating that prompts fit within context window
    - Checking for context overflow conditions
    """

    def __init__(self, token_counter: TokenCounter) -> None:
        """Initialize with a token counter implementation.
        
        Args:
            token_counter: Implementation-specific token counter.
        """
        self._token_counter = token_counter

    def build_system_prompt(
        self,
        transcription: str,
        *,
        num_examples: int = 3,
    ) -> str:
        """Build system prompt from Jinja2 template.
        
        Args:
            transcription: The project description/transcription.
            fmt: Format for examples (Markdown, etc.).
            num_examples: Number of examples to include.
        
        Returns:
            Rendered system prompt.
        """
        from app.prompts.loader import _ENV

        template_root = "estimation/v1"
        system_template = _ENV.get_template(f"{template_root}/system.j2")

        context = {
            "output_format": "phases_table",
            "detail_level": None,
            "project_description": transcription,
            "project_type": None,
            "num_examples": num_examples,
        }

        system_prompt = system_template.render(**context).strip()
        return system_prompt

    def build_pre_call_system_prompt(self, transcription: str) -> str:
        """Build requirements extraction system prompt.
        
        Args:
            transcription: The project description/transcription.
        
        Returns:
            System prompt for requirements extraction.
        """
        system_prompt, _ = render_requirements_extraction_prompt(transcription)
        return system_prompt

    def validate_context_window(
        self,
        system_prompt: str,
        user_message: str,
        model: str,
        max_output_tokens: int,
        context_window: int,
    ) -> int:
        """Validate and count input tokens, checking for context overflow.
        
        Args:
            system_prompt: The system/context prompt.
            user_message: The user-provided message.
            model: The model name.
            max_output_tokens: Maximum output tokens reserved.
            context_window: Total context window size.
        
        Returns:
            Estimated input token count.
        
        Raises:
            LLMServiceError: If total tokens exceed context window.
        """
        input_tokens_est = self._token_counter.count_tokens(
            system_prompt,
            user_message,
            model,
        )
        total_tokens_est = input_tokens_est + max_output_tokens

        if total_tokens_est >= context_window:
            log.warning(
                "context_overflow",
                model=model,
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
                    f"'{model}' ({context_window} tokens)."
                ),
                413,
            )

        return input_tokens_est

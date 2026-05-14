"""TokenCounter: Abstract base for token counting across providers."""

from abc import ABC, abstractmethod


class TokenCounter(ABC):
    """Abstract interface for token counting.
    
    Each LLM provider may have different token counting logic.
    This abstraction allows providers to implement their own counting logic.
    """

    @abstractmethod
    def count_tokens(
        self,
        system_prompt: str,
        user_message: str,
        model: str,
    ) -> int:
        """Count tokens for a given system prompt and user message.
        
        Args:
            system_prompt: The system/context prompt.
            user_message: The user-provided message or transcription.
            model: The model name for provider-specific token calculations.
        
        Returns:
            Estimated token count.
        """
        ...

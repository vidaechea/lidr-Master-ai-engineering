"""ErrorMapper: Handles exception mapping to LLMServiceError."""

from typing import Any, Callable


class LLMServiceError(Exception):
    """Domain error for LLM service operations.
    
    Unified exception that wraps provider-specific errors into a consistent
    error contract for the rest of the application.
    """

    def __init__(self, error_type: str, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.status_code = status_code


class ErrorMapper:
    """Maps provider-specific exceptions to LLMServiceError."""

    @staticmethod
    def build_provider_error_mapping(
        *,
        provider_label: str,
        auth_error_type: type[Exception],
        rate_limit_type: type[Exception],
        bad_request_type: type[Exception],
        connection_type: type[Exception],
        internal_error_type: type[Exception],
    ) -> dict[type[Exception], tuple[str, str | Callable[[Exception], str], int]]:
        """Build a mapping of provider exceptions to (error_type, message, status_code).
        
        Args:
            provider_label: Human-readable provider name (e.g., "OpenAI").
            auth_error_type: Exception class for authentication errors.
            rate_limit_type: Exception class for rate limit errors.
            bad_request_type: Exception class for bad request errors.
            connection_type: Exception class for connection errors.
            internal_error_type: Exception class for internal server errors.
        
        Returns:
            Mapping of exception type to (error_type, message, status_code) tuple.
            Message can be a string or callable that takes the exception.
        """
        return {
            auth_error_type: (
                "authentication_error",
                f"Invalid or missing {provider_label} API key.",
                401,
            ),
            rate_limit_type: (
                "rate_limit_error",
                "Rate limit reached or insufficient credit.",
                429,
            ),
            bad_request_type: (
                "bad_request_error",
                lambda error: f"Invalid request: {error.message}",
                400,
            ),
            connection_type: (
                "connection_error",
                lambda error: f"Connection or server error: {error}",
                503,
            ),
            internal_error_type: (
                "connection_error",
                lambda error: f"Connection or server error: {error}",
                503,
            ),
        }

    @staticmethod
    def map_exception(
        exc: Exception,
        mapping: dict[type[Exception], tuple[str, str | Callable[[Exception], str], int]],
    ) -> None:
        """Map an exception using the provided mapping or re-raise.
        
        Args:
            exc: Exception to map.
            mapping: Mapping of exception types to error details.
        
        Raises:
            LLMServiceError: If the exception is in the mapping.
            Exception: The original exception if not in the mapping.
        """
        for exc_type, (error_type, message, status_code) in mapping.items():
            if isinstance(exc, exc_type):
                resolved_message = message(exc) if callable(message) else message
                raise LLMServiceError(error_type, resolved_message, status_code)
        raise exc

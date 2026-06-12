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

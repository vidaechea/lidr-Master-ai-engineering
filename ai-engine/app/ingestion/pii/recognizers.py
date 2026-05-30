from __future__ import annotations

try:
    from presidio_analyzer import Pattern, PatternRecognizer
except Exception as exc:  # pragma: no cover
    raise RuntimeError(
        "presidio-analyzer is required for PII recognizers. Install project dependencies."
    ) from exc


class BudgetIdRecognizer(PatternRecognizer):
    def __init__(self) -> None:
        super().__init__(
            supported_entity="BUDGET_ID",
            name="BudgetIdRecognizer",
            patterns=[
                Pattern(
                    name="budget_id_pattern",
                    regex=r"\bBUD-\d{4}-\d{3}\b",
                    score=0.95,
                )
            ],
            supported_language="es",
        )


class ClientCodeRecognizer(PatternRecognizer):
    def __init__(self) -> None:
        super().__init__(
            supported_entity="CLIENT_CODE",
            name="ClientCodeRecognizer",
            patterns=[
                Pattern(
                    name="client_code_pattern",
                    regex=r"\bCLI-\d{4}\b",
                    score=0.95,
                )
            ],
            supported_language="es",
        )

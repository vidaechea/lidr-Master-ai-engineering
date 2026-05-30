from __future__ import annotations

from app.ingestion.parsers.budget_json import BudgetJsonParser
from app.ingestion.parsers.protocol import Parser
from app.ingestion.parsers.rate_card_xlsx import RateCardXlsxParser
from app.ingestion.parsers.transcript_txt import TranscriptTxtParser


class ParserRegistry:
    def __init__(self) -> None:
        self._by_format: dict[str, Parser] = {}

    def register(self, parser: Parser) -> None:
        for fmt in parser.supported_formats:
            if fmt in self._by_format:
                raise ValueError(
                    f"Format {fmt!r} already has a registered parser ({type(self._by_format[fmt]).__name__})"
                )
            self._by_format[fmt] = parser

    def get(self, fmt: str) -> Parser:
        try:
            return self._by_format[fmt]
        except KeyError as exc:
            raise KeyError(f"No parser registered for format {fmt!r}") from exc

    def formats(self) -> set[str]:
        return set(self._by_format)


def default_registry() -> ParserRegistry:
    registry = ParserRegistry()
    registry.register(BudgetJsonParser())
    registry.register(TranscriptTxtParser())
    registry.register(RateCardXlsxParser())
    return registry

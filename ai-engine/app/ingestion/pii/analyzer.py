from __future__ import annotations

from functools import lru_cache

from app.config import settings


@lru_cache
def build_analyzer():
    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "presidio-analyzer is required. Install dependencies for Session 06 PII support."
        ) from exc

    from app.ingestion.pii.recognizers import BudgetIdRecognizer, ClientCodeRecognizer

    provider = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "es", "model_name": settings.presidio_spacy_model}],
        }
    )
    engine = AnalyzerEngine(
        nlp_engine=provider.create_engine(),
        supported_languages=["es"],
    )
    engine.registry.add_recognizer(BudgetIdRecognizer())
    engine.registry.add_recognizer(ClientCodeRecognizer())
    return engine

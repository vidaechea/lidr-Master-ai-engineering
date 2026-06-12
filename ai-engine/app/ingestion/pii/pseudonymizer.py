from __future__ import annotations

import hashlib
import hmac
import random
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.ingestion.pii.mapping_store import MappingStore


@dataclass(frozen=True)
class AppliedMapping:
    entity_type: str
    original_hash: str
    pseudonym: str
    start: int
    end: int


@dataclass(frozen=True)
class PseudonymizationResult:
    pseudonymized_text: str
    applied: list[AppliedMapping]


class ConsistentPseudonymizer:
    def __init__(
        self,
        *,
        analyzer: Any,
        mapping_store: MappingStore,
        salt: str,
        faker_locale: str = "es_ES",
        language: str = "es",
    ) -> None:
        self._analyzer = analyzer
        self._store = mapping_store
        self._salt = salt.encode("utf-8")
        self._language = language
        try:
            from faker import Faker

            self._faker = Faker(faker_locale)
            self._faker.seed_instance(0)
            name_factory: Callable[[], str] = self._faker.name
            email_factory: Callable[[], str] = self._faker.ascii_company_email
            city_factory: Callable[[], str] = self._faker.city
            fallback_factory: Callable[[], str] = lambda: f"REDACTED-{self._faker.uuid4()[:8]}"  # noqa: E731
        except Exception:  # pragma: no cover - fallback path when Faker is not installed
            name_factory = lambda: f"Persona-{random.randint(1000, 9999)}"  # noqa: E731
            email_factory = lambda: f"anon-{random.randint(1000, 9999)}@example.local"  # noqa: E731
            city_factory = lambda: f"Ciudad-{random.randint(100, 999)}"  # noqa: E731
            fallback_factory = lambda: f"REDACTED-{uuid.uuid4().hex[:8]}"  # noqa: E731

        self._fallback_factory = fallback_factory
        self._generators: dict[str, Callable[[], str]] = {
            "PERSON": name_factory,
            "EMAIL_ADDRESS": email_factory,
            "LOCATION": city_factory,
            "BUDGET_ID": lambda: (
                f"BUD-{random.randint(2020, 2029)}-{random.randint(0, 999):03d}"
            ),
            "CLIENT_CODE": lambda: f"CLI-{random.randint(0, 9999):04d}",
        }

    def pseudonymize(self, text: str, *, entities: list[str] | None = None) -> PseudonymizationResult:
        results = self._analyzer.analyze(
            text=text,
            language=self._language,
            entities=entities,
        )
        if not results:
            return PseudonymizationResult(pseudonymized_text=text, applied=[])

        results.sort(key=lambda r: r.end, reverse=True)

        out = text
        applied: list[AppliedMapping] = []
        for r in results:
            original_value = text[r.start : r.end]
            entity_type = r.entity_type
            original_hash = self._hash(original_value)
            factory = self._generators.get(entity_type, self._fallback_pseudonym)
            pseudonym = self._store.lookup_or_create(
                entity_type=entity_type,
                original_hash=original_hash,
                new_pseudonym_factory=factory,
            )
            out = out[: r.start] + pseudonym + out[r.end :]
            applied.append(
                AppliedMapping(
                    entity_type=entity_type,
                    original_hash=original_hash,
                    pseudonym=pseudonym,
                    start=r.start,
                    end=r.end,
                )
            )

        return PseudonymizationResult(pseudonymized_text=out, applied=applied)

    def _hash(self, value: str) -> str:
        return hmac.new(self._salt, value.encode("utf-8"), hashlib.sha256).hexdigest()

    def _fallback_pseudonym(self) -> str:
        return self._fallback_factory()

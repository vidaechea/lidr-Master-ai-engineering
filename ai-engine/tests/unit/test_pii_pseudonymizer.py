from __future__ import annotations

from dataclasses import dataclass

from app.ingestion.pii.mapping_store import InMemoryMappingStore
from app.ingestion.pii.pseudonymizer import ConsistentPseudonymizer


@dataclass
class _Entity:
    start: int
    end: int
    entity_type: str


class _FakeAnalyzer:
    def analyze(self, text: str, language: str, entities=None):
        _ = language
        _ = entities
        name_start = text.index("Laura Fernandez")
        name_end = name_start + len("Laura Fernandez")
        name2_start = text.index("Laura Fernandez", name_end)
        name2_end = name2_start + len("Laura Fernandez")
        budget_start = text.index("BUDGET-2024-0001")
        budget_end = budget_start + len("BUDGET-2024-0001")
        return [
            _Entity(start=name_start, end=name_end, entity_type="PERSON"),
            _Entity(start=name2_start, end=name2_end, entity_type="PERSON"),
            _Entity(start=budget_start, end=budget_end, entity_type="BUDGET_ID"),
        ]


def test_consistent_pseudonymizer_keeps_same_value_for_same_entity() -> None:
    text = "Laura Fernandez revisa BUDGET-2024-0001 y Laura Fernandez confirma."
    pseudo = ConsistentPseudonymizer(
        analyzer=_FakeAnalyzer(),
        mapping_store=InMemoryMappingStore(),
        salt="test-salt",
        faker_locale="es_ES",
    )

    result = pseudo.pseudonymize(text)

    person_aliases = [a.pseudonym for a in result.applied if a.entity_type == "PERSON"]
    assert len(person_aliases) == 2
    assert person_aliases[0] == person_aliases[1]
    assert "Laura Fernandez" not in result.pseudonymized_text


def test_inmemory_mapping_store_forget_removes_mapping() -> None:
    store = InMemoryMappingStore()

    first = store.lookup_or_create("PERSON", "hash-1", lambda: "Alias Uno")
    assert first == "Alias Uno"

    removed = store.forget("PERSON", "hash-1")
    assert removed is True

    second = store.lookup_or_create("PERSON", "hash-1", lambda: "Alias Dos")
    assert second == "Alias Dos"

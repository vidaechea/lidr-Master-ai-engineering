#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("PSEUDONYM_HASH_SALT", "demo-salt")

from app.ingestion.pii import ConsistentPseudonymizer, InMemoryMappingStore, build_analyzer  # noqa: E402

TRANSCRIPT = ROOT / "data" / "seed" / "transcripts" / "transcripcion_2025-02-03_betanorte.txt"


def main() -> int:
    if not TRANSCRIPT.exists():
        print(f"ERROR: no existe {TRANSCRIPT}")
        return 1

    pseudo = ConsistentPseudonymizer(
        analyzer=build_analyzer(),
        mapping_store=InMemoryMappingStore(),
        salt=os.environ["PSEUDONYM_HASH_SALT"],
    )
    result = pseudo.pseudonymize(TRANSCRIPT.read_text(encoding="utf-8"))

    print(f"Transcripcion: {TRANSCRIPT.name}")
    print("\n--- Texto pseudonimizado (primeros 400 chars) ---")
    print(result.pseudonymized_text[:400])

    print(f"\n--- Mappings aplicados ({len(result.applied)}) ---")
    for m in result.applied[:12]:
        print(f"  {m.entity_type:14} -> {m.pseudonym}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

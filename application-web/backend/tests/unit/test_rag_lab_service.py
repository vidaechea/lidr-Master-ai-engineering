from __future__ import annotations

import json

from app.services.rag_lab_service import load_sample_budgets


def test_load_sample_budgets_reads_json_array(tmp_path):
    sample = tmp_path / "budgets.json"
    sample.write_text(json.dumps([{"budget_id": "BUD-1"}]), encoding="utf-8")

    budgets = load_sample_budgets(sample)

    assert budgets == [{"budget_id": "BUD-1"}]
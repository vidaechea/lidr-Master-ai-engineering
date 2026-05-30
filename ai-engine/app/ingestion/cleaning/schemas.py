from __future__ import annotations

import importlib
from typing import Any

BUDGET_ID_PATTERN = r"^BUD-\d{4}-\d{3}$"

def _build_schema() -> Any:
    pa = importlib.import_module("pandera.pandas")
    check_cls = getattr(pa, "Check")
    column_cls = getattr(pa, "Column")
    dataframe_schema_cls = getattr(pa, "DataFrameSchema")

    return dataframe_schema_cls(
        columns={
            "budget_id": column_cls(
                str,
                checks=check_cls.str_matches(BUDGET_ID_PATTERN),
                nullable=False,
                required=True,
            ),
        },
        strict=False,
        coerce=True,
    )


try:
    BudgetRecord = _build_schema()
except Exception:  # pragma: no cover
    class _MissingSchema:
        @staticmethod
        def validate(*args, **kwargs):
            raise RuntimeError("pandera is required for cleaning validation")

    BudgetRecord = _MissingSchema()

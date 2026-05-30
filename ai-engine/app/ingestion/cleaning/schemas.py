from __future__ import annotations

import importlib
from typing import Any

BUDGET_ID_PATTERN = r"^BUDGET-\d{4}-\d{4}$"
CLIENT_CODE_PATTERN = r"^CLI-\d{4}$"

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
            "client_name": column_cls(
                str,
                nullable=True,
                required=True,
            ),
            "client_code": column_cls(
                str,
                checks=check_cls.str_matches(CLIENT_CODE_PATTERN),
                nullable=False,
                required=True,
            ),
            "currency": column_cls(
                str,
                checks=check_cls.isin(["EUR", "USD", "GBP"]),
                nullable=False,
                required=True,
            ),
            "total_amount": column_cls(
                float,
                checks=[check_cls.ge(0), check_cls.le(10_000_000)],
                nullable=False,
                required=True,
            ),
            "signed_at": column_cls(
                "datetime64[ns]",
                nullable=False,
                required=True,
            ),
        },
        strict=True,
        coerce=False,
    )


try:
    BudgetRecord = _build_schema()
except Exception:  # pragma: no cover
    class _MissingSchema:
        @staticmethod
        def validate(*args, **kwargs):
            raise RuntimeError("pandera is required for cleaning validation")

    BudgetRecord = _MissingSchema()

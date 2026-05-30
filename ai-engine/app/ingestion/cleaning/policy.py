from __future__ import annotations

from dataclasses import dataclass, field
import importlib
from typing import Any

import pandas as pd

from app.ingestion.cleaning.schemas import BudgetRecord

QUARANTINE_CHECKS = {
    "not_nullable",
    "no_default",
    "column_in_dataframe",
}
DISCARD_CHECKS = {
    "in_range",
    "less_than_or_equal_to",
    "greater_than_or_equal_to",
    "isin",
    "str_matches",
}


@dataclass
class ValidationResult:
    valid: pd.DataFrame
    quarantined: pd.DataFrame
    discarded: pd.DataFrame
    report: dict[str, Any] = field(default_factory=dict)


def validate_with_policy(df: pd.DataFrame) -> ValidationResult:
    if df.empty:
        return ValidationResult(
            valid=df.copy(),
            quarantined=df.iloc[0:0].copy(),
            discarded=df.iloc[0:0].copy(),
            report={"input_rows": 0},
        )

    try:
        validated = BudgetRecord.validate(df, lazy=True)
        return ValidationResult(
            valid=validated,
            quarantined=df.iloc[0:0].copy(),
            discarded=df.iloc[0:0].copy(),
            report={
                "input_rows": len(df),
                "valid_rows": len(validated),
                "quarantined_rows": 0,
                "discarded_rows": 0,
                "failures_by_check": {},
            },
        )
    except Exception as err:
        try:
            pa_errors = importlib.import_module("pandera.errors")
        except Exception as exc:
            raise RuntimeError(
                "pandera is required for validate_with_policy"
            ) from exc
        if isinstance(err, getattr(pa_errors, "SchemaErrors")):
            return _route_failures(df, err)
        raise


def _route_failures(df: pd.DataFrame, err: Any) -> ValidationResult:
    failure_cases = err.failure_cases.copy()
    indices_quarantine: set[int] = set()
    indices_discard: set[int] = set()
    failures_by_check: dict[str, int] = {}

    for _, row in failure_cases.iterrows():
        check_name = str(row.get("check", "unknown"))
        failures_by_check[check_name] = failures_by_check.get(check_name, 0) + 1
        idx = row.get("index")
        if idx is None or pd.isna(idx):
            continue
        try:
            row_idx = int(idx)
        except (TypeError, ValueError):
            continue

        if any(disc in check_name for disc in DISCARD_CHECKS):
            indices_discard.add(row_idx)
        elif any(quar in check_name for quar in QUARANTINE_CHECKS):
            indices_quarantine.add(row_idx)
        else:
            indices_quarantine.add(row_idx)

    indices_quarantine -= indices_discard
    discarded_mask = df.index.isin(indices_discard)
    quarantined_mask = df.index.isin(indices_quarantine)
    valid_mask = ~(discarded_mask | quarantined_mask)

    return ValidationResult(
        valid=df.loc[valid_mask].copy(),
        quarantined=df.loc[quarantined_mask].copy(),
        discarded=df.loc[discarded_mask].copy(),
        report={
            "input_rows": len(df),
            "valid_rows": int(valid_mask.sum()),
            "quarantined_rows": int(quarantined_mask.sum()),
            "discarded_rows": int(discarded_mask.sum()),
            "failures_by_check": failures_by_check,
        },
    )

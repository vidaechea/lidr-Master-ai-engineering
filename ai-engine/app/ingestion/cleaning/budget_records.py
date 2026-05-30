from __future__ import annotations

import hashlib
import json
from typing import Iterable

import pandas as pd

NULL_PLACEHOLDERS = {"TBD", "N/A", "n/a", "tbd", "", "null", "None", "-"}


def clean_budget_records(records: Iterable[dict]) -> pd.DataFrame:
    df = pd.DataFrame(list(records))
    if df.empty:
        return df

    # Clean project_summary field if present
    if "project_summary" in df.columns:
        df["project_summary"] = df["project_summary"].apply(
            lambda v: pd.NA if (isinstance(v, str) and v.strip() in NULL_PLACEHOLDERS) else v
        )

    # Clean nested client_metadata.name field if the structure exists
    if "client_metadata" in df.columns:
        def clean_metadata(meta):
            if not isinstance(meta, dict):
                return meta
            if "name" in meta and isinstance(meta["name"], str):
                if meta["name"].strip() in NULL_PLACEHOLDERS:
                    meta["name"] = None
            return meta
        df["client_metadata"] = df["client_metadata"].apply(clean_metadata)

    # Ensure total_estimated_hours is numeric
    if "total_estimated_hours" in df.columns:
        df["total_estimated_hours"] = pd.to_numeric(df["total_estimated_hours"], errors="coerce")

    # Deduplication and sorting by budget_id
    if "budget_id" in df.columns:
        df["content_hash"] = df.apply(_content_hash, axis=1)
        df = df.sort_values(by="budget_id", na_position="first")
        df = df.drop_duplicates(subset=["budget_id"], keep="last").reset_index(drop=True)

    return df


def _content_hash(row: pd.Series) -> str:
    payload = {
        k: (None if (isinstance(v, float) and pd.isna(v)) else _serializable(v))
        for k, v in row.items()
        if k != "content_hash"
    }
    encoded = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _serializable(value):
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value

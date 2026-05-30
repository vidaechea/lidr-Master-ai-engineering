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

    for column in ("client_name", "contact", "contact_email", "notes"):
        if column in df.columns:
            df[column] = df[column].apply(
                lambda v: pd.NA if (isinstance(v, str) and v.strip() in NULL_PLACEHOLDERS) else v
            )

    if "currency" in df.columns:
        df["currency"] = df["currency"].astype("string").str.upper()

    if "signed_at" in df.columns:
        df["signed_at"] = pd.to_datetime(df["signed_at"], errors="coerce", dayfirst=True)

    if "total_amount" in df.columns:
        df["total_amount"] = pd.to_numeric(df["total_amount"], errors="coerce")

    if {"budget_id", "signed_at"}.issubset(df.columns):
        df["content_hash"] = df.apply(_content_hash, axis=1)
        df = df.sort_values(by=["budget_id", "signed_at"], na_position="first")
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

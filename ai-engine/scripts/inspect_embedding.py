#!/usr/bin/env python3
"""CLI script to inspect a single OpenAI embedding vector.

Usage:
    python scripts/inspect_embedding.py --text "OAuth 2.0 authentication backend..."
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402

DEFAULT_TEXT = "OAuth 2.0 authentication backend with JWT tokens for fintech mobile app"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect an OpenAI embedding vector.")
    parser.add_argument(
        "--text",
        default=DEFAULT_TEXT,
        help="Text to embed.",
    )
    parser.add_argument(
        "--model",
        default="text-embedding-3-small",
        help="Embedding model to use.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    text = args.text.strip()
    if not text:
        print("ERROR: --text must not be empty", file=sys.stderr)
        return 1

    if not settings.openai_api_key:
        print("ERROR: OPENAI_API_KEY environment variable not set", file=sys.stderr)
        return 1

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        response = client.embeddings.create(model=args.model, input=text)
        embedding = response.data[0].embedding

        print(f"Model: {args.model}")
        print(f"Text: {text}")
        print(f"Dimensions: {len(embedding)}")
        print(f"First 5 values: {embedding[:5]}")
        print(f"Last 5 values: {embedding[-5:]}")
        print(f"Value type: {type(embedding[0]).__name__}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
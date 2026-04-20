"""Anthropic Claude API client."""

import os
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()


class AnthropicClient:
    """Client for Anthropic Claude API."""

    # Available models with pricing (input/output per 1M tokens)
    MODELS = {
        "claude-haiku-4-5-20251001": {"input":1.00, "output": 5.00},
        "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
        "claude-opus-4-7": {"input": 15.0, "output": 75.0},
    }
    
    DEFAULT_MODEL = "claude-sonnet-4-6"

    def __init__(self, api_key: Optional[str] = None):
        """Initialize with API key from parameter or environment."""
        if api_key is None:
            api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()

        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment or .env file")

        self.client = Anthropic(api_key=api_key)

    def query(
        self,
        message: str,
        instructions: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 1000,
    ) -> Dict[str, Any]:
        """
        Query Anthropic Claude API.

        Args:
            message: User message.
            instructions: System instructions.
            model: Model name. Uses DEFAULT_MODEL if not specified.
            temperature: Sampling temperature (0-1).
            max_tokens: Maximum output tokens.

        Returns:
            Dict with 'content' and metadata, or 'error' if failed.
        """
        if model is None:
            model = self.DEFAULT_MODEL
            
        try:
            kwargs = {
                "model": model,
                "messages": [{"role": "user", "content": message}],
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            
            if instructions:
                kwargs["system"] = instructions

            response = self.client.messages.create(**kwargs)

            # Check if the response was truncated
            stop_reason = response.stop_reason
            if stop_reason == "max_tokens":
                print("⚠️  Response truncated (max_tokens reached)")

            prices = self.MODELS.get(model, {"input": 0, "output": 0})
            cost = (
                (response.usage.input_tokens / 1_000_000) * prices["input"]
                + (response.usage.output_tokens / 1_000_000) * prices["output"]
            )

            return {
                "content": response.content[0].text,
                "model": response.model,
                "id": response.id,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "stop_reason": stop_reason,
                "cost_usd": cost,
            }

        except Exception as e:
            return {"error": f"{type(e).__name__}: {str(e)}"}


if __name__ == "__main__":
    client = AnthropicClient()
    result = client.query(
        message="How long would a PostgreSQL to Aurora migration take?",
        instructions="You are a software estimation consultant. Be concise.",
    )
    
    if "error" in result:
        print(f"Error: {result['error']}")
    else:
        print(result["content"])
        print(f"\nTokens: {result['input_tokens']} in, {result['output_tokens']} out")
        print(f"Stop reason: {result['stop_reason']}")
        print(f"Cost: ${result['cost_usd']:.6f}")

"""OpenAI Responses API client."""

import os
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


class OpenAIClient:
    """Client for OpenAI Responses API."""

    # Available models with pricing (input/output per 1M tokens)
    MODELS = {
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "gpt-4-turbo": {"input": 10.0, "output": 30.0},
        "gpt-3.5-turbo": {"input": 0.5, "output": 1.5},
    }
    
    DEFAULT_MODEL = "gpt-3.5-turbo"

    def __init__(self, api_key: Optional[str] = None):
        """Initialize with API key from parameter or environment."""
        if api_key is None:
            api_key = os.getenv("OPENAI_API_KEY", "").strip()

        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment or .env file")

        self.client = OpenAI(api_key=api_key)

    def query(
        self,
        message: str,
        instructions: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 1000,
    ) -> Dict[str, Any]:
        """
        Query OpenAI Responses API.

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
            response = self.client.responses.create(
                model=model,
                instructions=instructions,
                input=message,
                temperature=temperature,
                max_output_tokens=max_tokens,
                store=False,
            )

            if response.status != "completed":
                return {"error": f"Response not completed: {response.status}"}

            prices = self.MODELS.get(model, {"input": 0, "output": 0})
            cost = (
                (response.usage.input_tokens / 1_000_000) * prices["input"]
                + (response.usage.output_tokens / 1_000_000) * prices["output"]
            )

            return {
                "content": response.output_text,
                "model": response.model,
                "id": response.id,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "cost_usd": cost,
            }

        except Exception as e:
            return {"error": f"{type(e).__name__}: {str(e)}"}


if __name__ == "__main__":
    client = OpenAIClient()
    result = client.query(
        message="How long would a PostgreSQL to Aurora migration take?",
        instructions="Be concise.",
    )
    
    if "error" in result:
        print(f"Error: {result['error']}")
    else:
        print(result["content"])
        print(f"\nTokens: {result['input_tokens']} in, {result['output_tokens']} out")
        print(f"Cost: ${result['cost_usd']:.6f}")

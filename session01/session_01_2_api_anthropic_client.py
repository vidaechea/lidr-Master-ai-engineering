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
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        stop_sequences: Optional[list] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tools: Optional[list] = None,
        tool_choice: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Query Anthropic Claude API with comprehensive parameters.

        Args:
            message: User message.
            instructions: System instructions.
            model: Model name. Uses DEFAULT_MODEL if not specified.
            temperature: Sampling temperature (0-1). Default 0.3.
            max_tokens: Maximum output tokens. Default 1000.
            top_p: Nucleus sampling parameter (0-1). Overrides temperature if set.
            top_k: Only sample from top k most likely next tokens.
            stop_sequences: List of strings where API stops generating.
            metadata: Custom metadata dictionary for the request.
            tools: List of tools available for the model (for tool use/function calling).
            tool_choice: Control how tools are used {"type": "auto"|"any"|"tool", "name": "..."}

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
            }
            
            # Temperature is NOT added if top_p or top_k is specified
            # (Anthropic API: cannot specify temperature with top_p or top_k)
            if top_p is None and top_k is None:
                kwargs["temperature"] = temperature
            
            if instructions:
                kwargs["system"] = instructions
            
            # Optional sampling parameters
            if top_p is not None:
                kwargs["top_p"] = top_p
            if top_k is not None:
                kwargs["top_k"] = top_k
            if stop_sequences is not None:
                kwargs["stop_sequences"] = stop_sequences
            
            # Metadata for tracking/debugging
            if metadata is not None:
                kwargs["metadata"] = metadata
            
            # Tool use parameters (function calling)
            if tools is not None:
                kwargs["tools"] = tools
            if tool_choice is not None:
                kwargs["tool_choice"] = tool_choice

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
                "temperature": temperature,
                "top_p": top_p,
                "top_k": top_k,
                "stop_sequences": stop_sequences,
                "tools_used": tools is not None,
            }

        except Exception as e:
            return {"error": f"{type(e).__name__}: {str(e)}"}


if __name__ == "__main__":
    client = AnthropicClient()
    
    # Example 1: Basic query
    print("=" * 60)
    print("Example 1: Basic Query")
    print("=" * 60)
    result = client.query(
        message="How long would a PostgreSQL to Aurora migration take?",
        instructions="You are a software estimation consultant. Be concise.",
    )
    if "error" in result:
        print(f"❌ Error: {result['error']}")
    else:
        print(f"Response: {result['content']}\n")
        print(f"Tokens - Input: {result['input_tokens']}, Output: {result['output_tokens']}")
        print(f"Cost: ${result['cost_usd']:.6f}\n")
    
    # Example 2: With sampling parameters (more creative/diverse)
    print("=" * 60)
    print("Example 2: More Creative (high temperature)")
    print("=" * 60)
    result = client.query(
        message="Write a short creative story about AI",
        instructions="Be imaginative and creative.",
        temperature=0.9,  # Higher temperature = more creative
        top_p=0.95,       # Nucleus sampling
        max_tokens=500,
    )
    if "error" in result:
        print(f"❌ Error: {result['error']}")
    else:
        print(f"Response: {result['content']}\n")
        print(f"Parameters used - Temperature: {result['temperature']}, Top-P: {result['top_p']}\n")
    
    # Example 3: With stop sequences
    print("=" * 60)
    print("Example 3: With Stop Sequences")
    print("=" * 60)
    result = client.query(
        message="List three benefits of Python",
        instructions="Number each item.",
        stop_sequences=["\n4."],  # Stop at item 4
        max_tokens=300,
    )
    if "error" in result:
        print(f"❌ Error: {result['error']}")
    else:
        print(f"Response: {result['content']}\n")
        print(f"Stop sequences applied: {result['stop_sequences']}\n")
    
    # Example 4: Deterministic (low temperature, top_k)
    print("=" * 60)
    print("Example 4: Deterministic Response (low temperature)")
    print("=" * 60)
    result = client.query(
        message="What is 2+2?",
        instructions="Answer with just the number.",
        temperature=0.0,  # Deterministic
        top_k=1,          # Only pick top token
        max_tokens=10,
    )
    if "error" in result:
        print(f"❌ Error: {result['error']}")
    else:
        print(f"Response: {result['content']}\n")
        print(f"Parameters - Temperature: {result['temperature']}, Top-K: {result['top_k']}\n")
        print(f"Stop reason: {result['stop_reason']}")
        print(f"Cost: ${result['cost_usd']:.6f}")

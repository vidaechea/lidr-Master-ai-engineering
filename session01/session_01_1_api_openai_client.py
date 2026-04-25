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

        # Multi-turn conversation state
        self._last_response_id: Optional[str] = None
        self._turn_count: int = 0
        self._total_cost: float = 0.0

    # ------------------------------------------------------------------
    # Multi-turn conversation
    # ------------------------------------------------------------------

    def chat(
        self,
        message: str,
        instructions: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = 0.7,
        max_tokens: int = 1000,
        top_p: Optional[float] = None,
        reasoning_effort: Optional[str] = None,
        tools: Optional[list] = None,
        continue_conversation: bool = True,
    ) -> Dict[str, Any]:
        """
        Send a message keeping conversation context via previous_response_id.

        Args:
            message: User message.
            instructions: System instructions (recommended on the first turn).
            model: Model name. Uses DEFAULT_MODEL if not specified.
            temperature: Sampling temperature (0-1). Set to None when using top_p.
            max_tokens: Maximum output tokens.
            top_p: Nucleus sampling probability (0-1). Alternative to temperature.
            reasoning_effort: Reasoning effort for reasoning-capable models ("low", "medium", "high").
            tools: List of built-in tool configs, e.g. [{"type": "web_search_preview"}].
            continue_conversation: If True, chains to the previous turn context.

        Returns:
            Dict with 'content', metadata, turn stats, and 'response_id'.
        """
        model = model or self.DEFAULT_MODEL
        self._turn_count += 1

        params: Dict[str, Any] = {
            "model": model,
            "input": message,
            "instructions": instructions,
            "max_output_tokens": max_tokens,
            "store": True,  # Required so OpenAI stores the response for chaining
        }

        # top_p and temperature are mutually exclusive
        if top_p is not None:
            params["top_p"] = top_p
        else:
            params["temperature"] = temperature

        if reasoning_effort is not None:
            params["reasoning"] = {"effort": reasoning_effort}

        if tools is not None:
            params["tools"] = tools

        if continue_conversation and self._last_response_id:
            params["previous_response_id"] = self._last_response_id

        try:
            response = self.client.responses.create(**params)

            if response.status != "completed":
                return {"error": f"Response not completed: {response.status}"}

            self._last_response_id = response.id

            prices = self.MODELS.get(model, {"input": 0, "output": 0})
            turn_cost = (
                (response.usage.input_tokens / 1_000_000) * prices["input"]
                + (response.usage.output_tokens / 1_000_000) * prices["output"]
            )
            self._total_cost += turn_cost

            return {
                "content": response.output_text,
                "model": response.model,
                "response_id": response.id,
                "turn": self._turn_count,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "turn_cost_usd": turn_cost,
                "total_cost_usd": self._total_cost,
            }

        except Exception as e:
            return {"error": f"{type(e).__name__}: {str(e)}"}

    def reset(self) -> None:
        """Reset conversation context (start a new thread)."""
        self._last_response_id = None
        self._turn_count = 0
        self._total_cost = 0.0

    @property
    def last_response_id(self) -> Optional[str]:
        """ID of the last stored response (useful for branching)."""
        return self._last_response_id

    # ------------------------------------------------------------------

    def query(
        self,
        message: str,
        instructions: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = 0.3,
        max_tokens: int = 1000,
        top_p: Optional[float] = None,
        reasoning_effort: Optional[str] = None,
        tools: Optional[list] = None,
    ) -> Dict[str, Any]:
        """
        Query OpenAI Responses API.

        Args:
            message: User message.
            instructions: System instructions.
            model: Model name. Uses DEFAULT_MODEL if not specified.
            temperature: Sampling temperature (0-1). Set to None when using top_p.
            max_tokens: Maximum output tokens.
            top_p: Nucleus sampling probability (0-1). Alternative to temperature.
            reasoning_effort: Reasoning effort for reasoning-capable models ("low", "medium", "high").
            tools: List of built-in tool configs, e.g. [{"type": "web_search_preview"}].

        Returns:
            Dict with 'content' and metadata, or 'error' if failed.
        """
        if model is None:
            model = self.DEFAULT_MODEL

        params: Dict[str, Any] = {
            "model": model,
            "instructions": instructions,
            "input": message,
            "max_output_tokens": max_tokens,
            "store": False,
        }

        if top_p is not None:
            params["top_p"] = top_p
        else:
            params["temperature"] = temperature

        if reasoning_effort is not None:
            params["reasoning"] = {"effort": reasoning_effort}

        if tools is not None:
            params["tools"] = tools

        try:
            response = self.client.responses.create(**params)

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
    # ----------------------------------------------------------------
    # Demo 1 — single query (original behaviour)
    # ----------------------------------------------------------------
    SYSTEM_PROMPT = """You are a senior software project estimation consultant with 20 years of experience.

Rules:
- Always respond in Spanish
- Use technical terminology without simplifying
- When providing an estimate, always include a range (optimistic/pessimistic)
- If you lack sufficient information to estimate, ask before guessing
- Write in prose, no unnecessary bullet points"""

    USER_MESSAGE = "How long would it take to migrate a Rails monolith to microservices?"

    client = OpenAIClient()
    result = client.query(
        message=USER_MESSAGE,
        instructions=SYSTEM_PROMPT,
        model="gpt-4o-mini",
        temperature=0.3,
        max_tokens=1000,
        # top_p=1.0,          # Uncomment and remove temperature to use top_p instead
        # reasoning_effort="medium",  # Only for reasoning-capable models (o1, o3, etc.)
        # tools=[{"type": "web_search_preview"}],
    )

    if "error" in result:
        print(f"Error: {result['error']}")
    else:
        print(result["content"])
        print(f"\nTokens: {result['input_tokens']} in, {result['output_tokens']} out")
        print(f"Cost: ${result['cost_usd']:.6f}")

    # ----------------------------------------------------------------
    # Demo 2 — multi-turn conversation via previous_response_id
    # ----------------------------------------------------------------
    print("\n" + "=" * 60)
    print("Multi-turn demo")
    print("=" * 60)

    TECH_SYSTEM = "You are a technical assistant. Always answer in Spanish."

    # Turn 1 — no previous context yet
    r1 = client.chat(
        message="What is a REST API?",
        instructions=TECH_SYSTEM,
        model="gpt-4o-mini",
    )
    if "error" in r1:
        print(f"Error: {r1['error']}")
    else:
        print(f"\n[Turn {r1['turn']}] response_id: {r1['response_id']}")
        print(r1["content"])
        print(f"Tokens: {r1['input_tokens']} in / {r1['output_tokens']} out | cost: ${r1['turn_cost_usd']:.6f}")

    # Turn 2 — OpenAI recovers context automatically via previous_response_id
    r2 = client.chat(
        message="What is the difference with GraphQL?",
        model="gpt-4o-mini",
    )
    if "error" in r2:
        print(f"Error: {r2['error']}")
    else:
        print(f"\n[Turn {r2['turn']}] previous_response_id → {r1['response_id']}")
        print(r2["content"])
        print(f"Tokens: {r2['input_tokens']} in / {r2['output_tokens']} out | cost: ${r2['turn_cost_usd']:.6f}")
        print(f"Total conversation cost: ${r2['total_cost_usd']:.6f}")

    # Reset — start a new thread
    client.reset()
    print("\n[reset] Conversation context cleared.")

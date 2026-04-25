"""OpenAI Responses API client."""

import json
import os
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from openai import OpenAI
import tiktoken

load_dotenv()


class OpenAIClient:
    """Client for OpenAI Responses API."""

    # Model registry: pricing ($/1M tokens), input/output ratio, tiktoken encoding, reasoning flag, context window (tokens)
    # ratio = output_price / input_price — captures output cost asymmetry (higher ratio → output is proportionally more expensive)
    MODELS = {
        "gpt-3.5-turbo":      {"input": 0.50,  "output": 1.50,  "ratio": 1.50 / 0.50,  "encoding": "cl100k_base", "reasoning": False, "context_window":  16_385},
        "gpt-4-turbo":        {"input": 10.0,  "output": 30.0,  "ratio": 30.0 / 10.0,  "encoding": "cl100k_base", "reasoning": False, "context_window": 128_000},
        "gpt-4o-mini":        {"input": 0.15,  "output": 0.60,  "ratio": 0.60 / 0.15,  "encoding": "o200k_base",  "reasoning": False, "context_window": 128_000},
        "gpt-5.4-mini":       {"input": 0.75,  "output": 4.50,  "ratio": 4.50 / 0.75,  "encoding": "o200k_base",  "reasoning": False, "context_window": 128_000},
        "gpt-5.4":            {"input": 2.50,  "output": 15.00, "ratio": 15.00 / 2.50, "encoding": "o200k_base",  "reasoning": False, "context_window": 128_000},
        "o3-mini":            {"input": 1.10,  "output": 4.40,  "ratio": 4.40 / 1.10,  "encoding": "o200k_base",  "reasoning": True,  "context_window": 200_000},
        "o3":                 {"input": 10.0,  "output": 40.0,  "ratio": 40.0 / 10.0,  "encoding": "o200k_base",  "reasoning": True,  "context_window": 200_000},
        "o4-mini":            {"input": 1.10,  "output": 4.40,  "ratio": 4.40 / 1.10,  "encoding": "o200k_base",  "reasoning": True,  "context_window": 200_000},
        "o4-mini-2025-04-16": {"input": 1.10,  "output": 4.40,  "ratio": 4.40 / 1.10,  "encoding": "o200k_base",  "reasoning": True,  "context_window": 200_000},
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

    # ------------------------------------------------------------------
    # Reasoning API
    # ------------------------------------------------------------------

    def reason(
        self,
        message: str,
        instructions: Optional[str] = None,
        model: str = "o4-mini",
        reasoning_effort: str = "medium",
        verbosity: str = "low",
        max_output_tokens: int = 2000,
    ) -> Dict[str, Any]:
        """
        Query a reasoning-capable model using the dedicated reasoning controls.

        Reasoning models (o1, o3, o4-mini, …) do NOT support temperature or top_p.
        Instead they expose:
          - reasoning.effort  ("low" | "medium" | "high") — controls how deeply the
            model thinks before answering.  Higher effort → better answers, more tokens.
          - text.verbosity    ("low" | "medium" | "high") — controls how verbose the
            final answer is.  "low" keeps responses concise.

        Args:
            message: User question or prompt.
            instructions: Optional system instructions.
            model: A reasoning-capable model, e.g. "o4-mini", "o3", "o1".
            reasoning_effort: Depth of internal reasoning ("low", "medium", "high").
            verbosity: Length of the final answer ("low", "medium", "high").
            max_output_tokens: Hard cap on output tokens (includes reasoning tokens).

        Returns:
            Dict with 'content', token usage, reasoning tokens, and cost metadata.
        """
        params: Dict[str, Any] = {
            "model": model,
            "input": message,
            "reasoning": {"effort": reasoning_effort},   # controls reasoning depth
            "text": {"format": {"type": "text"}},        # plain-text output
            "max_output_tokens": max_output_tokens,
            "store": False,
        }

        if instructions:
            params["instructions"] = instructions

        try:
            response = self.client.responses.create(**params)

            if response.status != "completed":
                return {"error": f"Response not completed: {response.status}"}

            # Reasoning models report reasoning tokens separately
            reasoning_tokens = getattr(
                getattr(response.usage, "output_tokens_details", None),
                "reasoning_tokens",
                None,
            )

            prices = self.MODELS.get(model, {"input": 0, "output": 0})
            cost = (
                (response.usage.input_tokens / 1_000_000) * prices["input"]
                + (response.usage.output_tokens / 1_000_000) * prices["output"]
            )

            return {
                "content": response.output_text,
                "model": response.model,
                "id": response.id,
                "reasoning_effort": reasoning_effort,
                "verbosity": verbosity,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "reasoning_tokens": reasoning_tokens,
                "cost_usd": cost,
            }

        except Exception as e:
            return {"error": f"{type(e).__name__}: {str(e)}"}


# ----------------------------------------------------------------
# Token estimation
# ----------------------------------------------------------------

def estimate_call_tokens(
    instructions: str,
    messages: list,
    model: str = "gpt-4o-mini",
) -> int:
    """
    Estimate the number of input tokens for a Responses API call.
    This is an approximation — the actual count includes special tokens
    added by the API that we can't perfectly replicate locally.
    Uses the correct tiktoken encoding for each model from the registry.
    """
    model_cfg = OpenAIClient.MODELS.get(model, {"encoding": "o200k_base"})
    enc = tiktoken.get_encoding(model_cfg["encoding"])

    total = len(enc.encode(instructions or "")) + 4  # overhead for system message formatting
    for msg in messages:
        total += len(enc.encode(msg["content"])) + 4  # overhead per message (role tokens, delimiters)
    total += 2  # priming tokens for the assistant's response
    return total


# ----------------------------------------------------------------
# Demo functions
# ----------------------------------------------------------------

def demo_single_query(client: "OpenAIClient") -> None:
    """Demo 1 — single query."""
    SYSTEM_PROMPT = """You are a senior software project estimation consultant with 20 years of experience.

Rules:
- Always respond in Spanish
- Use technical terminology without simplifying
- When providing an estimate, always include a range (optimistic/pessimistic)
- If you lack sufficient information to estimate, ask before guessing
- Write in prose, no unnecessary bullet points"""

    user_msg = "How long would it take to migrate a Rails monolith to microservices?"
    model = "gpt-4o-mini"

    estimated = estimate_call_tokens(SYSTEM_PROMPT, [{"role": "user", "content": user_msg}], model)
    prices = OpenAIClient.MODELS[model]
    print(f"Estimated input tokens : {estimated}")
    print(f"Estimated input cost   : ${(estimated / 1_000_000) * prices['input']:.6f}\n")

    result = client.query(
        message=user_msg,
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
        print(f"\nEstimated input tokens : {estimated}")
        print(f"Actual input tokens    : {result['input_tokens']}  (delta: {result['input_tokens'] - estimated:+d})")
        print(f"Output tokens          : {result['output_tokens']}")
        print(f"Cost: ${result['cost_usd']:.6f}")


def demo_multi_turn(client: "OpenAIClient") -> None:
    """Demo 2 — multi-turn conversation via previous_response_id."""
    print("\n" + "=" * 60)
    print("Multi-turn demo")
    print("=" * 60)

    TECH_SYSTEM = "You are a technical assistant. Always answer in Spanish."

    # Turn 1 — no previous context yet
    t1_msg = "What is a REST API?"
    t1_estimated = estimate_call_tokens(TECH_SYSTEM, [{"role": "user", "content": t1_msg}], "gpt-4o-mini")
    print(f"[Turn 1] Estimated input tokens: {t1_estimated}")
    r1 = client.chat(
        message=t1_msg,
        instructions=TECH_SYSTEM,
        model="gpt-4o-mini",
    )
    if "error" in r1:
        print(f"Error: {r1['error']}")
    else:
        print(f"[Turn {r1['turn']}] response_id: {r1['response_id']}")
        print(r1["content"])
        print(f"Actual input tokens: {r1['input_tokens']} (delta: {r1['input_tokens'] - t1_estimated:+d}) | out: {r1['output_tokens']} | cost: ${r1['turn_cost_usd']:.6f}")

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


def demo_reasoning(client: "OpenAIClient") -> None:
    """Demo 3 — reasoning model with reasoning + verbosity controls."""
    print("\n" + "=" * 60)
    print("Reasoning demo (o4-mini)")
    print("=" * 60)

    r_result = client.reason(
        message="Should we use microservices?",
        instructions="You are a technical analyst. Answer in Spanish.",
        model="o4-mini",
        reasoning_effort="medium",   # "low" | "medium" | "high"
        verbosity="low",             # "low" | "medium" | "high"
        max_output_tokens=2000,
    )

    if "error" in r_result:
        print(f"Error: {r_result['error']}")
    else:
        print(r_result["content"])
        print(f"\nModel           : {r_result['model']}")
        print(f"Reasoning effort: {r_result['reasoning_effort']}")
        print(f"Verbosity       : {r_result['verbosity']}")
        print(f"Tokens in/out   : {r_result['input_tokens']} / {r_result['output_tokens']}")
        if r_result["reasoning_tokens"] is not None:
            print(f"Reasoning tokens: {r_result['reasoning_tokens']}")
        print(f"Cost            : ${r_result['cost_usd']:.6f}")


def demo_tokenization() -> None:
    """Demo 4 — tokenization and BPE with tiktoken."""
    print("\n" + "=" * 60)
    print("Tokenization and BPE (tiktoken)")
    print("=" * 60)

    DEMO_MODEL = "gpt-4o-mini"
    enc = tiktoken.get_encoding(OpenAIClient.MODELS[DEMO_MODEL]["encoding"])
    print(f"Encoding: {enc.name}  (used by {DEMO_MODEL})")

    # --- Basic example ---
    text = "PostgreSQL migration"
    tokens = enc.encode(text)

    print(f"\nText:      '{text}'")
    print(f"Token IDs: {tokens}")
    print(f"Count:     {len(tokens)} tokens")
    print()

    for token_id in tokens:
        decoded = enc.decode([token_id])
        print(f"  ID {token_id:>6d} → '{decoded}'")

    # --- Text comparison: how BPE handles subwords ---
    print("\n" + "-" * 40)
    print("Tokenization comparison (BPE subwords)")
    print("-" * 40)

    examples = [
        "tokenization",
        "tokenizations",
        "tokenizer",
        "untokenizable",
        "hello world",
        "Hola mundo",
        "こんにちは",          # Japanese — more tokens per character
    ]

    for t in examples:
        ids = enc.encode(t)
        parts = [enc.decode([i]) for i in ids]
        print(f"  {len(ids):>2d} tokens | {str(parts):<45s} | '{t}'")

    # --- Cost impact: tokens vs characters ---
    print("\n" + "-" * 40)
    price_per_million = OpenAIClient.MODELS[DEMO_MODEL]["input"]
    print(f"Cost estimate by token count ({DEMO_MODEL} input: ${price_per_million}/1M)")
    print("-" * 40)
    sample_texts = [
        "Explain BPE in one sentence.",
        "Explica BPE en una oracion.",
        "Explain Byte Pair Encoding (BPE) tokenization in detail, " * 5,
    ]

    for st in sample_texts:
        n = len(enc.encode(st))
        cost = (n / 1_000_000) * price_per_million
        preview = st[:50] + "..." if len(st) > 50 else st
        print(f"  {n:>4d} tokens | ${cost:.8f} | '{preview}'")

    # --- Vocabulary size across tokenizer generations ---
    print("\n" + "-" * 40)
    print("Vocabulary size by encoding (derived from MODELS registry)")
    print("-" * 40)

    # gpt2 is not in MODELS but included for historical comparison
    extra = {"gpt2": "gpt-2 (2019, legacy)"}

    # Collect unique encodings from MODELS and which models use them
    seen: Dict[str, list] = {}
    for model_name, cfg in OpenAIClient.MODELS.items():
        seen.setdefault(cfg["encoding"], []).append(model_name)

    for enc_name, label in extra.items():
        enc_v = tiktoken.get_encoding(enc_name)
        print(f"  {enc_name:15s} → {enc_v.n_vocab:>7,} tokens  ({label})")

    for enc_name, models in seen.items():
        enc_v = tiktoken.get_encoding(enc_name)
        print(f"  {enc_name:15s} → {enc_v.n_vocab:>7,} tokens  (used by: {', '.join(models)})")

    # --- Token density of real source code ---
    print("\n" + "-" * 40)
    print("Token density: source code vs structured text")
    print("-" * 40)

    code_samples = {
        "Python function": '''def calculate_total(items, tax_rate=0.21):
    subtotal = sum(item.price for item in items)
    return subtotal * (1 + tax_rate)''',

        "JSON payload": '''{
    "project": "payment-migration",
    "team_size": 5,
    "estimated_weeks": 12,
    "confidence": "medium",
    "risks": ["data-loss", "downtime", "integration-failures"]
}''',

        "SQL query": '''SELECT u.name, COUNT(o.id) as order_count, SUM(o.total) as revenue
FROM users u
JOIN orders o ON u.id = o.user_id
WHERE o.created_at >= '2024-01-01'
GROUP BY u.name
HAVING SUM(o.total) > 1000
ORDER BY revenue DESC;''',
    }

    for label, code in code_samples.items():
        tokens = enc.encode(code)
        words = len(code.split())
        chars = len(code)
        ratio = chars / len(tokens) if tokens else 0
        print(f"  {label:20s}: {len(tokens):>4d} tokens  {chars:>4d} chars  {words:>3d} words  ({ratio:.1f} chars/token)")

    # --- Indentation overhead: compact vs pretty-print JSON ---
    print("\n" + "-" * 40)
    print("Indentation overhead: compact vs pretty-print JSON")
    print("-" * 40)

    data = {
        "project": "migration",
        "tasks": [
            {"name": "schema-analysis", "hours": 40},
            {"name": "data-transfer",   "hours": 80},
            {"name": "testing",         "hours": 60},
        ],
    }

    compact = json.dumps(data)
    pretty  = json.dumps(data, indent=2)

    compact_tokens = enc.encode(compact)
    pretty_tokens  = enc.encode(pretty)

    print(f"  Compact JSON: {len(compact):>4d} chars → {len(compact_tokens):>3d} tokens")
    print(f"  Pretty JSON:  {len(pretty):>4d} chars → {len(pretty_tokens):>3d} tokens")
    overhead_tokens = len(pretty_tokens) - len(compact_tokens)
    overhead_pct    = (len(pretty_tokens) / len(compact_tokens) - 1) * 100
    print(f"  Overhead:     {overhead_tokens:+d} extra tokens ({overhead_pct:.0f}% more)")


def demo_pricing() -> None:
    """Demo 6 — input/output pricing asymmetry across models (USD per 1M tokens)."""
    print("\n" + "=" * 60)
    print("Pricing asymmetry (USD / 1M tokens, April 2026)")
    print("=" * 60)

    print(f"\n{'Model':25s} {'Input':>10s} {'Output':>10s} {'Ratio':>8s} {'Reasoning':>10s}")
    print("-" * 68)

    for model, cfg in OpenAIClient.MODELS.items():
        reasoning = "yes" if cfg["reasoning"] else "no"
        print(
            f"{model:25s}"
            f" ${cfg['input']:>8.2f}"
            f" ${cfg['output']:>8.2f}"
            f" {cfg['ratio']:>7.1f}x"
            f" {reasoning:>10s}"
        )

    print()
    # Highlight the model with the highest output/input asymmetry
    most_asymmetric = max(OpenAIClient.MODELS, key=lambda m: OpenAIClient.MODELS[m]["ratio"])
    r = OpenAIClient.MODELS[most_asymmetric]["ratio"]
    print(f"Most asymmetric model: {most_asymmetric} (output is {r:.1f}x more expensive than input)")

    # Show cost impact for a realistic workload: 10k input tokens, 1k output tokens
    print("\n" + "-" * 68)
    print("Estimated cost: 10,000 input tokens + 1,000 output tokens")
    print("-" * 68)
    for model, cfg in OpenAIClient.MODELS.items():
        cost = (10_000 / 1_000_000) * cfg["input"] + (1_000 / 1_000_000) * cfg["output"]
        print(f"  {model:25s} ${cost:.6f}")


def demo_context_windows() -> None:
    """Demo 5 — context window sizes across models in the registry."""
    print("\n" + "=" * 60)
    print("Context window sizes (OpenAI models)")
    print("=" * 60)

    # Rough estimate: 1 page ≈ 500 words ≈ 670 tokens
    TOKENS_PER_PAGE = 670

    print(f"\n{'Model':25s} {'Context window':>15s} {'~Pages of text':>15s} {'Reasoning':>10s}")
    print("-" * 68)

    for model, cfg in OpenAIClient.MODELS.items():
        tokens = cfg.get("context_window", 0)
        pages = tokens / TOKENS_PER_PAGE
        reasoning = "yes" if cfg["reasoning"] else "no"
        print(f"{model:25s} {tokens:>15,} {pages:>14,.0f} {reasoning:>10s}")

    print()
    # Summary: largest context window in the registry
    best_model = max(OpenAIClient.MODELS, key=lambda m: OpenAIClient.MODELS[m].get("context_window", 0))
    best_tokens = OpenAIClient.MODELS[best_model]["context_window"]
    print(f"Largest context: {best_model} ({best_tokens:,} tokens ≈ {best_tokens / TOKENS_PER_PAGE:,.0f} pages)")


if __name__ == "__main__":
    client = OpenAIClient()

    #demo_single_query(client)
    #demo_multi_turn(client)
    #demo_reasoning(client)
    #demo_tokenization()
    #demo_context_windows()
    demo_pricing()
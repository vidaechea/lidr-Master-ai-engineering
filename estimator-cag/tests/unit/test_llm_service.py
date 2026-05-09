"""Unit tests for the llm_service facade — provider-agnostic validation and delegation."""
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.services.base_llm_service as svc
from app.services.base_llm_service import LLMServiceError, ModelInfo, ParsedResponse, estimate, estimate_call_tokens


class DummyStreamService(svc.BaseLLMService):
    def __init__(self) -> None:
        super().__init__()
        self.turns: list[tuple[str, str]] = []

    def _get_model_info(self, model: str | None) -> tuple[str, ModelInfo]:
        return "dummy-model", ModelInfo(
            input_price=1.0,
            output_price=1.0,
            context_window=10_000,
            reasoning=False,
        )

    def _count_tokens(self, system_prompt: str, user_message: str, model: str) -> int:
        return 5

    def _build_api_params(
        self,
        *,
        resolved_model: str,
        system_prompt: str,
        transcription: str,
        model_info: dict[str, Any],
        temperature: float | None,
        top_p: float | None,
        top_k: int | None,
        reasoning_effort: str,
        max_output_tokens: int,
        continue_conversation: bool,
    ) -> dict[str, Any]:
        return {
            "model": resolved_model,
            "input": transcription,
            "max_output_tokens": max_output_tokens,
        }

    async def _call_provider(self, api_params: dict[str, Any]) -> Any:
        return {
            "estimation": "Requirements",
            "input_tokens": 3,
            "output_tokens": 2,
            "response_id": "precall-1",
            "finish_reason": "stop",
        }

    def _parse_provider_response(self, response: Any, *, is_reasoning: bool) -> ParsedResponse:
        return ParsedResponse(
            estimation=response["estimation"],
            response_id=response["response_id"],
            input_tokens=response["input_tokens"],
            output_tokens=response["output_tokens"],
            reasoning_tokens=None,
            finish_reason=response.get("finish_reason", "stop"),
        )

    async def _call_provider_stream(
        self,
        api_params: dict[str, Any],
        *,
        is_reasoning: bool,
    ) -> AsyncIterator[str]:
        for delta in ("Hello ", "world"):
            yield delta
        self._stream_partial = ParsedResponse(
            estimation="",
            response_id="stream-1",
            input_tokens=10,
            output_tokens=5,
            reasoning_tokens=None,
            finish_reason="stop",
            truncated=False,
        )

    def _on_turn_complete(self, transcription: str, assistant_content: str) -> None:
        self.turns.append((transcription, assistant_content))

    @property
    def _provider_name(self) -> str:
        return "dummy"



# --------------------------------------------------------------------------- #
# estimate_call_tokens — delegation to active service
# --------------------------------------------------------------------------- #

class TestEstimateCallTokens:
    def test_returns_positive_integer(self):
        tokens = estimate_call_tokens("You are an expert.", "Build a CRUD app.")
        assert isinstance(tokens, int)
        assert tokens > 0

    def test_longer_inputs_produce_more_tokens(self):
        short = estimate_call_tokens("system", "short")
        long = estimate_call_tokens("system", "short " * 200)
        assert long > short


# --------------------------------------------------------------------------- #
# estimate — shared validation (via facade, provider-agnostic)
# --------------------------------------------------------------------------- #

class TestFacadeValidation:
    async def test_raises_when_both_temperature_and_top_p_set(self):
        with pytest.raises(ValueError, match="mutually exclusive"):
            await estimate("test", temperature=0.5, top_p=0.9)

    async def test_raises_when_model_not_in_registry(self):
        with pytest.raises(ValueError, match="Unknown model"):
            await estimate("test", model="nonexistent-model")

    async def test_raises_llm_service_error_on_context_overflow(self):
        with patch.object(svc._get_active_service(), "_count_tokens", return_value=999_999_999):
            with pytest.raises(LLMServiceError) as exc_info:
                await estimate("test")
        assert exc_info.value.status_code == 413
        assert "overflow" in exc_info.value.error_type


# --------------------------------------------------------------------------- #
# _raise_service_error — fallback behavior
# --------------------------------------------------------------------------- #


class TestRaiseServiceError:
    def test_unmapped_exception_is_re_raised(self) -> None:
        service = DummyStreamService()
        mapping = {KeyError: ("key_error", "message", 400)}
        with pytest.raises(ValueError):
            service._raise_service_error(ValueError("boom"), mapping)


# --------------------------------------------------------------------------- #
# estimate_stream — shared behavior
# --------------------------------------------------------------------------- #


class TestEstimateStream:
    @pytest.mark.asyncio
    async def test_populates_last_stream_result(self) -> None:
        service = DummyStreamService()
        chunks: list[str] = []
        async for delta in service.estimate_stream("hello"):
            chunks.append(delta)

        expected_cost = round((10 + 5) / 1_000_000, 8)
        assert "".join(chunks) == "Hello world"
        assert service._last_stream_result["estimation"] == "Hello world"
        assert service._last_stream_result["turn_cost_usd"] == expected_cost
        assert service._last_stream_result["total_cost_usd"] == expected_cost
        assert service._last_stream_result["requirements"] is None

    @pytest.mark.asyncio
    async def test_continue_conversation_tracks_turns(self) -> None:
        service = DummyStreamService()
        async for _ in service.estimate_stream(
            "hello",
            continue_conversation=True,
            pre_call=True,
        ):
            pass

        assert service._last_response_id == "stream-1"
        assert service._turn_count == 1
        assert service._total_cost > 0
        assert service.turns == [("Requirements", "Hello world")]
        assert service._last_stream_result["requirements"] == "Requirements"

    @pytest.mark.asyncio
    async def test_stream_context_overflow_raises(self) -> None:
        service = DummyStreamService()
        tiny_context = ModelInfo(
            input_price=1.0,
            output_price=1.0,
            context_window=6,
            reasoning=False,
        )
        with patch.object(service, "_get_model_info", return_value=("dummy-model", tiny_context)):
            with pytest.raises(LLMServiceError) as exc_info:
                async for _ in service.estimate_stream("hello", max_output_tokens=5):
                    pass
        assert exc_info.value.error_type == "context_overflow"

    @pytest.mark.asyncio
    async def test_stream_error_is_propagated(self) -> None:
        service = DummyStreamService()

        async def _broken_stream(*_args: Any, **_kwargs: Any) -> AsyncIterator[str]:
            raise LLMServiceError("stream_error", "boom")
            yield  # pragma: no cover - required for async generator type

        with patch.object(service, "_call_provider_stream", _broken_stream):
            with pytest.raises(LLMServiceError) as exc_info:
                async for _ in service.estimate_stream("hello"):
                    pass
        assert exc_info.value.error_type == "stream_error"

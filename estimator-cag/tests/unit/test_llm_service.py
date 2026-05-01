"""Unit tests for the llm_service facade — provider-agnostic validation and delegation."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.services.base_llm_service as svc
from app.services.base_llm_service import estimate, estimate_call_tokens



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

    async def test_returns_error_dict_on_context_overflow(self):
        with patch.object(svc._active_service, "_count_tokens", return_value=999_999_999):
            result = await estimate("test")
        assert result.get("error") is True
        assert result.get("status_code") == 413
        assert "overflow" in result.get("type", "")

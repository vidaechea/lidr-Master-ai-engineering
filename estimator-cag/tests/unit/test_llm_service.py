from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.context.examples import EXAMPLE_HEADER_TEMPLATE
from app.services.llm_service import ROLE_SYSTEM, ROLE_USER, estimate


class TestEstimate:
    @pytest.fixture
    def mock_openai_response(self):
        message = MagicMock()
        message.content = "## Estimate: Sample Project\n\n1. Backend: 40 hours\n\n**Total: 40 hours**"
        choice = MagicMock()
        choice.message = message
        response = MagicMock()
        response.choices = [choice]
        return response

    async def test_returns_string(self, mock_openai_response):
        with patch(
            "app.services.llm_service.client.chat.completions.create",
            new=AsyncMock(return_value=mock_openai_response),
        ):
            result = await estimate("Build a simple API")
            assert isinstance(result, str)

    async def test_returns_llm_message_content(self, mock_openai_response):
        with patch(
            "app.services.llm_service.client.chat.completions.create",
            new=AsyncMock(return_value=mock_openai_response),
        ):
            result = await estimate("Build a simple API")
            assert result == mock_openai_response.choices[0].message.content

    async def test_calls_openai_with_user_description(self, mock_openai_response):
        description = "Build a real-time chat application"
        with patch(
            "app.services.llm_service.client.chat.completions.create",
            new=AsyncMock(return_value=mock_openai_response),
        ) as mock_create:
            await estimate(description)
            call_kwargs = mock_create.call_args.kwargs
            messages = call_kwargs["messages"]
            user_message = next(m for m in messages if m["role"] == ROLE_USER)
            assert user_message["content"] == description

    async def test_injects_examples_as_system_message(self, mock_openai_response):
        with patch(
            "app.services.llm_service.client.chat.completions.create",
            new=AsyncMock(return_value=mock_openai_response),
        ) as mock_create:
            await estimate("Build something")
            call_kwargs = mock_create.call_args.kwargs
            messages = call_kwargs["messages"]
            system_message = next(m for m in messages if m["role"] == ROLE_SYSTEM)
            # The system prompt must contain injected examples
            assert EXAMPLE_HEADER_TEMPLATE.format(index=1) in system_message["content"]

    async def test_sends_exactly_two_messages(self, mock_openai_response):
        with patch(
            "app.services.llm_service.client.chat.completions.create",
            new=AsyncMock(return_value=mock_openai_response),
        ) as mock_create:
            await estimate("Build something")
            messages = mock_create.call_args.kwargs["messages"]
            assert len(messages) == 2

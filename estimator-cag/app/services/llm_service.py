from openai import AsyncOpenAI
from app.config import settings
from app.context.examples import get_examples_context

ROLE_SYSTEM = "system"
ROLE_USER = "user"

client = AsyncOpenAI(api_key=settings.openai_api_key)


async def estimate(description: str) -> str:
    context = get_examples_context()
    response = await client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": ROLE_SYSTEM, "content": context},
            {"role": ROLE_USER, "content": description},
        ],
    )
    return response.choices[0].message.content

from openai import AsyncOpenAI
from app.config import settings
from app.context.examples import get_examples_context

client = AsyncOpenAI(api_key=settings.openai_api_key)


async def estimate(description: str) -> str:
    context = get_examples_context()
    response = await client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": context},
            {"role": "user", "content": description},
        ],
    )
    return response.choices[0].message.content

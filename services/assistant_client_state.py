from openai import AsyncOpenAI
from config import settings

client: AsyncOpenAI = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
assistant_id: str | None = None
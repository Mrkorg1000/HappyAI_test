import json
import os
from typing import Optional
from openai import AsyncOpenAI
from config import settings
from aiogram.fsm.context import FSMContext


client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


ASSISTANT_ID = None


async def initialize_assistant(client: AsyncOpenAI, model: str = "gpt-4o") -> str:
    """
    Инициализирует ассистента, если он еще не создан.
    
    Параметры:
    - client (AsyncOpenAI): Клиент OpenAI API.
    - model (str, optional): Название модели (по умолчанию "gpt-4o").
    
    Возвращает:
    - str: ID созданного ассистента.
    """
    global ASSISTANT_ID

    if ASSISTANT_ID is None:
        assistant = await client.beta.assistants.create(
            name="Persistent Assistant",
            instructions="Отвечай на вопросы кратко и по существу.",
            model=model,
            tools=[{"type": "file_search"}]  # Добавление инструмента поиска по файлам
        )
        ASSISTANT_ID = assistant.id
        
    else:
        # Обновление существующего ассистента для добавления file_search
        assistant = await client.beta.assistants.update(
            assistant_id=ASSISTANT_ID,
            tools=[{"type": "file_search"}]  # Добавление инструмента поиска по файлам
        )
    return ASSISTANT_ID


async def get_single_response(question: str, model: str = "gpt-4o") -> tuple[Optional[str], Optional[str]]:
    """
    Отправляет вопрос в OpenAI GPT-4o и получает ответ, возвращая также thread_id.
    """
    assistant_id = await initialize_assistant(client, model)
    thread = await client.beta.threads.create()

    try:
        await client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=question
        )

        await client.beta.threads.runs.create_and_poll(
            thread_id=thread.id,
            assistant_id=assistant_id
        )

        messages = await client.beta.threads.messages.list(thread_id=thread.id)
        answer: Optional[str] = None

        for message in messages.data:
            if message.role == "assistant":
                answer = message.content[0].text.value
                break

        return answer, thread.id

    except Exception:
        return None, thread.id

    finally:
        await client.beta.threads.delete(thread_id=thread.id)
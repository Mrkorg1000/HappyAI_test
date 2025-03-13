import asyncio
from typing import Optional
from openai import AsyncOpenAI
from config import settings


async def get_single_response(question: str, model: str = "gpt-4o") -> Optional[str]:
    """
    Отправляет вопрос в OpenAI GPT-4o и получает ответ.

    Параметры:
    - question (str): Вопрос, который будет отправлен модели.
    - model (str, optional): Название модели (по умолчанию "gpt-4o").

    Возвращает:
    - Optional[str]: Ответ модели, если запрос успешен, иначе None.

    Исключения:
    - Может выбросить исключение, если API OpenAI не отвечает или произошла ошибка.
    """

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    # Создаем временного ассистента
    assistant = await client.beta.assistants.create(
        name="One-time Assistant",
        instructions="Отвечай на вопросы кратко и по существу.",
        model=model
    )

    # Создаем новый поток для этого вопроса
    thread = await client.beta.threads.create()

    try:
        # Добавляем сообщение от пользователя
        await client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=question
        )

        # Запускаем обработку запроса
        run = await client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=assistant.id
        )

        while True:
            run_status = await client.beta.threads.runs.retrieve(
                thread_id=thread.id, run_id=run.id
            )
            if run_status.status == "completed":
                break
            await asyncio.sleep(0.5)  # Ожидание между проверками

        messages = await client.beta.threads.messages.list(thread_id=thread.id)
        answer: Optional[str] = None

        for message in messages.data:
            if message.role == "assistant":
                answer = message.content[0].text.value
                break

        return answer

    finally:
        # Удаляем созданные ресурсы
        await client.beta.assistants.delete(assistant_id=assistant.id)
        await client.beta.threads.delete(thread_id=thread.id)

from typing import Optional
from openai import AsyncOpenAI
from config import settings


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
            model=model
        )
        ASSISTANT_ID = assistant.id

    return ASSISTANT_ID


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

    assistant_id = await initialize_assistant(client, model)

    # Создаем новый поток для этого вопроса
    thread = await client.beta.threads.create()

    try:
        # Добавляем сообщение от пользователя
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

        return answer

    finally:
        await client.beta.threads.delete(thread_id=thread.id)

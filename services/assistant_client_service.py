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


# async def get_single_response(question: str, model: str = "gpt-4o") -> tuple[Optional[str], Optional[str]]:
#     """
#     Отправляет вопрос в OpenAI GPT-4o и получает ответ, возвращая также thread_id.
#     """
#     assistant_id = await initialize_assistant(client, model)
#     thread = await client.beta.threads.create()
#     try:
#         await client.beta.threads.messages.create(
#             thread_id=thread.id,
#             role="user",
#             content=question
#         )
        
#         await client.beta.threads.runs.create_and_poll(
#             thread_id=thread.id,
#             assistant_id=assistant_id
#         )
        
#         messages = await client.beta.threads.messages.list(thread_id=thread.id)
#         answer: Optional[str] = None
        
#         for message in messages.data:
#             if message.role == "assistant":
#                 text_content = message.content[0].text
#                 answer = text_content.value
                
#                 # Проверяем наличие аннотаций в сообщении
#                 if hasattr(text_content, 'annotations') and text_content.annotations:
#                     for annotation in text_content.annotations:
#                         if hasattr(annotation, 'file_citation'):
#                             # Получаем имя файла
#                             file_id = annotation.file_citation.file_id
#                             file_info = await client.files.retrieve(file_id)
#                             file_name = file_info.filename
                            
#                             # Ищем индекс цитаты, используя метаданные аннотации
#                             if hasattr(annotation, 'start_index') and hasattr(annotation, 'end_index'):
#                                 citation_text = answer[annotation.start_index:annotation.end_index]
#                                 # Заменяем цитированный текст на текст с указанием файла
#                                 answer = answer.replace(
#                                     citation_text, 
#                                     f"{citation_text} (из файла: {file_name})"
#                                 )
                
#                 break
                
#         return answer, thread.id
#     except Exception as e:
#         print(f"Ошибка при получении ответа: {e}")
#         return None, thread.id
#     finally:
#         await client.beta.threads.delete(thread_id=thread.id)

async def get_single_response(question: str, file_path: str = None, model: str = "gpt-4o") -> tuple[Optional[str], Optional[str]]:
    """
    Отправляет вопрос в OpenAI GPT-4o и получает ответ, возвращая также thread_id.
    Позволяет прикрепить файл к вопросу.
    
    Параметры:
    - question (str): Вопрос пользователя
    - file_path (str, optional): Путь к файлу для прикрепления
    - model (str, optional): Модель для использования
    
    Возвращает:
    - tuple[Optional[str], Optional[str]]: (ответ, thread_id)
    """
    assistant_id = await initialize_assistant(client, model)
    thread = await client.beta.threads.create()
    
    uploaded_file_id = None
    
    try:
        # Загружаем файл, если путь указан
        if file_path:
            with open(file_path, "rb") as file:
                uploaded_file = await client.files.create(
                    file=file,
                    purpose="assistants"
                )
                uploaded_file_id = uploaded_file.id
                print(f"Файл {file_path} загружен с ID: {uploaded_file_id}")
        
        # Создаем сообщение пользователя, прикрепляя файл при наличии
        message_params = {
            "thread_id": thread.id,
            "role": "user",
            "content": question
        }
        
        # Добавляем file_ids только если файл был загружен
        if uploaded_file_id:
            message_params["file_ids"] = [uploaded_file_id]
        
        await client.beta.threads.messages.create(**message_params)
        
        # Запускаем обработку
        run = await client.beta.threads.runs.create_and_poll(
            thread_id=thread.id,
            assistant_id=assistant_id
        )
        
        # Получаем ответ
        messages = await client.beta.threads.messages.list(thread_id=thread.id)
        answer: Optional[str] = None
        
        for message in messages.data:
            if message.role == "assistant":
                text_content = message.content[0].text
                answer = text_content.value
                
                # Проверяем наличие аннотаций в сообщении
                if hasattr(text_content, 'annotations') and text_content.annotations:
                    for annotation in text_content.annotations:
                        if hasattr(annotation, 'file_citation'):
                            # Получаем имя файла
                            file_id = annotation.file_citation.file_id
                            file_info = await client.files.retrieve(file_id)
                            file_name = file_info.filename
                            
                            # Ищем индекс цитаты, используя метаданные аннотации
                            if hasattr(annotation, 'start_index') and hasattr(annotation, 'end_index'):
                                citation_text = answer[annotation.start_index:annotation.end_index]
                                # Заменяем цитированный текст на текст с указанием файла
                                answer = answer.replace(
                                    citation_text, 
                                    f"{citation_text} (из файла: {file_name})"
                                )
                
                break
                
        return answer, thread.id
    except Exception as e:
        print(f"Ошибка при получении ответа: {e}")
        return None, thread.id
    finally:
        # Удаляем загруженный файл
        if uploaded_file_id:
            try:
                await client.files.delete(uploaded_file_id)
                print(f"Файл {uploaded_file_id} удален")
            except Exception as e:
                print(f"Ошибка при удалении файла: {e}")
        
        # Удаляем thread
        await client.beta.threads.delete(thread_id=thread.id)
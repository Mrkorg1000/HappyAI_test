import asyncio
from pathlib import Path
from typing import Optional
import aiohttp
from openai import AsyncOpenAI
import openai
from config import settings
from services.assistant_client_state import client, assistant_id


async def initialize_assistant(client: AsyncOpenAI, api_key: str, model: str = "gpt-4o", anxiety_file_path: str = None) -> str:
    """
    Инициализирует ассистента и настраивает vector store с файлом.

    Параметры:
    - client (AsyncOpenAI): Клиент OpenAI SDK.
    - api_key (str): Ключ API OpenAI.
    - model (str): Модель, например "gpt-4o".
    - anxiety_file_path (str): Путь к .docx файлу для загрузки в vector store.

    Возвращает:
    - str: ID ассистента.
    """
    from services.assistant_client_state import assistant_id

    headers = {
        "Authorization": f"Bearer {api_key}",
        "OpenAI-Beta": "assistants=v2",
        "Content-Type": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        # 1. Создание или обновление ассистента
        if assistant_id is None:
            assistant = await client.beta.assistants.create(
                name="Persistent Assistant",
                instructions=(
                    "Ты универсальный помощник. Отвечай на общие вопросы используя свои знания. "
                    "Когда тебя спрашивают о тревожности, тревоге, панических атаках или "
                    "связанных темах — используй информацию из прикрепленных материалов. "
                    "При цитировании из файлов всегда указывай название файла."
                ),
                model=model,
                tools=[{"type": "file_search"}]
            )
            assistant_id = assistant.id
        else:
            assistant = await client.beta.assistants.update(
                assistant_id=assistant_id,
                tools=[{"type": "file_search"}]
            )

        # 2. Создание vector store
        vector_store_payload = {"name": "Anxiety Vector Store"}
        async with session.post("https://api.openai.com/v1/vector_stores", headers=headers, json=vector_store_payload) as resp:
            vector_store = await resp.json()
            vector_store_id = vector_store["id"]

        # 3. Загрузка файла
        if anxiety_file_path:
            file_path = Path(anxiety_file_path)
            form_data = aiohttp.FormData()
            form_data.add_field("purpose", "assistants")
            form_data.add_field("file", file_path.open("rb"), filename=file_path.name)

            file_headers = {
                "Authorization": f"Bearer {api_key}"
            }

            async with session.post("https://api.openai.com/v1/files", headers=file_headers, data=form_data) as resp:
                file_data = await resp.json()
                file_id = file_data["id"]

            # 4. Добавление файла в vector store
            batch_payload = {"file_ids": [file_id]}
            async with session.post(
                f"https://api.openai.com/v1/vector_stores/{vector_store_id}/file_batches",
                headers=headers,
                json=batch_payload
            ) as resp:
                _ = await resp.json()

        # 5. Привязка vector store к ассистенту
        update_payload = {
            "tool_resources": {
                "file_search": {
                    "vector_store_ids": [vector_store_id]
                }
            }
        }
        async with session.post(
            f"https://api.openai.com/v1/assistants/{assistant_id}",
            headers=headers,
            json=update_payload
        ) as resp:
            _ = await resp.json()

    return assistant_id


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
    from services.assistant_client_state import assistant_id
    
    if assistant_id is None:
            assistant_id = await initialize_assistant(
        client,
        settings.OPENAI_API_KEY,
        model="gpt-4o",
        anxiety_file_path="anxiety.docx" 
    )
            
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
                for content in message.content:
                    if content.type == 'text':
                        answer = content.text.value
                        
                        if hasattr(content.text, 'annotations'):
                            annotations = sorted(
                                content.text.annotations,
                                key=lambda x: x.start_index,
                                reverse=True 
                            )
                            
                            for annotation in annotations:
                                if hasattr(annotation, 'file_citation'):
                                    try:
                                        file_id = annotation.file_citation.file_id
                                        file_info = await client.files.retrieve(file_id)
                                        file_name = file_info.filename
                                        
                                        end_pos = annotation.end_index
                                        answer = answer[:end_pos] + f' (из файла: {file_name})' + answer[end_pos:]
                                        
                                    except Exception as e:
                                        print(f"Ошибка при обработке аннотации: {e}")
               
                        break
                if answer:
                    break
                
        return answer, thread.id
                

    except Exception as e:
        print(f"Ошибка при получении ответа: {e}")
        return None, thread.id
    
    finally:
        # Удаляем временные ресурсы
        if uploaded_file_id:
            try:
                await client.files.delete(uploaded_file_id)
            except Exception as e:
                print(f"Ошибка при удалении временного файла: {e}")
        
        try:
            await client.beta.threads.delete(thread_id=thread.id)
        except Exception as e:
            print(f"Ошибка при удалении thread: {e}")
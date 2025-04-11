from io import BytesIO
from typing import Optional
import aiohttp
from services.assistant_client_service import client


async def text_to_audio(
    text: str,
    api_key: str,
    voice: str = "alloy",
    model: str = "tts-1"
) -> Optional[BytesIO]:
    """
    Преобразует текст в речь с использованием OpenAI TTS API.

    Параметры:
    - text (str): Текст для преобразования в речь.
    - api_key (str): OpenAI API ключ.
    - voice (str, optional): Голос для генерации (alloy, echo, fable, onyx, nova, shimmer). 
      По умолчанию: "alloy".
    - model (str, optional): Модель TTS (tts-1, tts-1-hd). По умолчанию: "tts-1".

    Возвращает:
    - BytesIO: Файлоподобный объект с аудиоданными (MP3), если запрос успешен.
    - None: В случае ошибки.
    """

    try:
        # Выполнение запроса на преобразование текста в речь
        response = await client.audio.speech.create(
            model=model,
            voice=voice,
            input=text
        )

        # Получение аудиоданных из ответа
        audio_bytes = response.content

        # Создание BytesIO объекта для хранения аудиоданных
        audio_file = BytesIO(audio_bytes)
        audio_file.name = "output.mp3"

        return audio_file

    except Exception as e:
        print(f"Ошибка при преобразовании текста в речь: {e}")
        return None

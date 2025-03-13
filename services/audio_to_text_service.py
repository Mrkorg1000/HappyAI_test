from io import BytesIO
from typing import Optional
from openai import AsyncOpenAI
from config import settings


client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


async def audio_to_text(audio_file: BytesIO) -> Optional[str]:
    """
    Преобразует аудиофайл в текст с использованием OpenAI Whisper API.

    Параметры:
    - audio_file (BytesIO): Файлоподобный объект с аудиофайлом (OGG, MP3, WAV и др.).

    Возвращает:
    - str: Распознанный текст, если запрос успешен.
    - None: В случае ошибки.

    Исключения:
    - Может выбросить исключение, если формат аудиофайла не поддерживается
      или произошла ошибка при обращении к API.
    """

    try:
        # Перематываем поток в начало (на всякий случай)
        audio_file.seek(0)
        audio_file.name = "audio.ogg"  

        # Отправляем аудиофайл в API Whisper
        question: str = await client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="text"
        )
        return question
    except Exception as e:
        print(f"Ошибка при конвертации аудио в текст: {e}")
        return None

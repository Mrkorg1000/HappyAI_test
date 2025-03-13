from io import BytesIO
from typing import Optional
import aiohttp


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

    url = "https://api.openai.com/v1/audio/speech"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "input": text,
        "voice": voice
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as response:
            if response.status == 200:
                audio_bytes: bytes = await response.read()
                audio_file = BytesIO(audio_bytes)
                audio_file.name = "output.mp3"
                return audio_file
            else:
                print(f"Ошибка: {response.status}")
                print(await response.text())
                return None

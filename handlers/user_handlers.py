import asyncio
from io import BytesIO
import json
from typing import Dict, List, Optional
from aiogram import Router, types
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram import F, types
from sqlalchemy.ext.asyncio import AsyncSession

from amplitude_dep import async_amplitude_track
from config import settings

from form import Form
from pg_db.database import async_session_maker
from services.assistant_client_service import client
from services.audio_to_text_service import audio_to_text
from services.assistant_client_service import get_single_response
from services.photo_service import analyze_mood
from services.values_service import save_user_values, user_has_values
from services.func_calling_service import VALUES_SYSTEM_PROMPT, tools
from services.text_to_audio_service import text_to_audio


user_router = Router()


@user_router.message(CommandStart())
async def start(message: types.Message) -> None:
    """
    Обрабатывает команду /start и отправляет приветственное сообщение пользователю.

    Параметры:
    - message (types.Message): Объект сообщения от пользователя.
    """
    await async_amplitude_track(
        user_id=message.from_user.id,
        event_type="start_command"
    )
    await message.answer(
        f"Привет! <b>{message.from_user.first_name}</b>\n"
        "Я отвечу на твои вопросы! Только голосовые!!!",
        parse_mode=ParseMode.HTML
    )
    await message.answer("А еще! Отправь мне фото с лицом, и я определю твое настроение.")


@user_router.message(lambda message: message.text)
async def process_text(message: types.Message) -> None:
    """
    Обрабатывает текстовые сообщения и уведомляет пользователя,
    что бот отвечает только на голосовые сообщения.

    Параметры:
    - message (types.Message): Объект текстового сообщения от пользователя.
    """
    await async_amplitude_track(
        user_id=message.from_user.id,
        event_type="text_message_rejected"
    )
    await message.answer(("Общение только голосом!\nИзвини, Брат, такое Задание 😔"))


@user_router.message(lambda message: message.voice,
                     ~StateFilter(Form.collecting_values),
)
async def process_voice_question(message: types.Message, state: FSMContext) -> None:
    """
    Обрабатывает голосовые сообщения: конвертирует их в текст,
    получает ответ от ассистента и отправляет ответ в виде голосового сообщения.

    Параметры:
    - message (types.Message): Объект голосового сообщения от пользователя.
    """
    await async_amplitude_track(
        user_id=message.from_user.id,
        event_type="voice_message_received"
    )
    
    voice: types.Voice = message.voice
    file_id: str = voice.file_id

    await message.answer("Секундочку, сейчас отвечу")

    # Скачиваем голосовое сообщение
    file: types.File = await message.bot.get_file(file_id)
    downloaded_file: BytesIO = await message.bot.download_file(file.file_path)

    # Преобразуем аудио в текст
    question_text: Optional[str] = await audio_to_text(downloaded_file)

    if question_text is None:
        await async_amplitude_track(
                user_id=message.from_user.id,
                event_type="voice_recognition_failed"
            )
        await message.answer("Не удалось распознать голосовое сообщение.")
        return

    # Получаем ответ от ассистента
    response_text, thread_id = await get_single_response(question_text)

    if response_text is None:
        await async_amplitude_track(
                user_id=message.from_user.id,
                event_type="assistant_response_failed"
            )
        await message.answer("Ошибка при получении ответа от ассистента.")
        return
    
    
    await state.update_data(thread_id=thread_id)


    # Преобразуем текст ответа в аудио
    audio_response: Optional[BytesIO] = await text_to_audio(response_text, api_key=settings.OPENAI_API_KEY)

    if audio_response:
        audio_response.seek(0)  # Перемещаем указатель в начало
        voice_file = types.BufferedInputFile(
            audio_response.getvalue(), filename="response.ogg"
        )
        await message.answer_voice(voice_file)
        await async_amplitude_track(
                user_id=message.from_user.id,
                event_type="voice_response_sent"
            )
    else:
        await async_amplitude_track(
                user_id=message.from_user.id,
                event_type="audio_generation_failed"
            )
        await message.answer("Ошибка при генерации аудио.")

    # await asyncio.sleep(3)
    
    telegram_id = message.from_user.id
    has_values = await user_has_values(telegram_id)
    if not has_values:
        await async_amplitude_track(
                user_id=message.from_user.id,
                event_type="values_collection_started"
            )
        user_name = message.from_user.first_name
        values_question = f"{user_name}, ответь пожалуйста, какие твои жизненные ценности. Можешь назвать несколько."
    
        audio_response: Optional[BytesIO] = await text_to_audio(values_question, api_key=settings.OPENAI_API_KEY)

        if audio_response:
            audio_response.seek(0)  # Перемещаем указатель в начало
            voice_file = types.BufferedInputFile(
                audio_response.getvalue(), filename="response.ogg"
            )
            await message.answer_voice(voice_file)
            
            await state.set_state(Form.collecting_values)
            await state.update_data(
                conversation_history=[],
                attempt_count=0
            )
            
        else:
            await message.answer("Ошибка при генерации аудио.")
        
        
@user_router.message(lambda message: message.voice, StateFilter(Form.collecting_values))
async def process_values(
    message: types.Message,
    state: FSMContext,
) -> None:
    """
    Обрабатывает голосовые сообщения от пользователя, которые содержат ответ на вопрос о жизненных ценностях.
    """
    await async_amplitude_track(
        user_id=message.from_user.id,
        event_type="values_processing_started"
    )
    
    voice: types.Voice = message.voice
    file_id: str = voice.file_id

    await message.answer("Секундочку, сейчас обработаю твои ценности")

    # Скачиваем голосовое сообщение
    file: types.File = await message.bot.get_file(file_id)
    downloaded_file: BytesIO = await message.bot.download_file(file.file_path)

    # Преобразуем аудио в текст
    values_text: Optional[str] = await audio_to_text(downloaded_file)

    if values_text is None:
        await async_amplitude_track(
                user_id=message.from_user.id,
                event_type="values_recognition_failed"
            )
        await message.answer("Не удалось распознать голосовое сообщение.")
        return
    
    state_data = await state.get_data()
    conversation_history: List[Dict[str, str]] = state_data.get("conversation_history", [])
    attempt_count: int = state_data.get("attempt_count", 0)
    
    # Добавляем текущий ответ пользователя в историю
    conversation_history.append({"role": "user", "content": values_text})
    
    # Формируем сообщения для API
    messages_for_api = [{"role": "system", "content": VALUES_SYSTEM_PROMPT}] + conversation_history
    
    try:
        response = await client.chat.completions.create(
            model="gpt-4",
            messages=messages_for_api,
            tools=tools,
            tool_choice="auto",
            temperature=0.5,
        )
        response_message = response.choices[0].message
        
        if response_message.tool_calls:
            for tool_call in response_message.tool_calls:
                if tool_call.function.name == "save_user_values":
                    values = json.loads(tool_call.function.arguments)["values"]
                    
                    async with async_session_maker() as session:
                        await save_user_values(session, message.from_user.id, values)
                    await async_amplitude_track(
                        user_id=message.from_user.id,
                        event_type="values_saved",
                        event_props={"values_count": len(values)}
                    )
                    await message.answer("Готово, Ваши ценности зафиксированы")
                    await state.clear()
                    return
                
        followup_question = response_message.content
        conversation_history.append(response_message.model_dump())
        
        if attempt_count >= 2:
            await message.answer("Давайте прервёмся. Вы можете вернуться к этому позже.")
            await state.clear()
            return
        
        audio = await text_to_audio(followup_question, settings.OPENAI_API_KEY)
        if audio:
            await async_amplitude_track(
                user_id=message.from_user.id,
                event_type="followup_question_sent"
            )
            await message.answer_voice(
                types.BufferedInputFile(audio.getvalue(), "followup.ogg")
            )

        # Обновляем состояние (увеличиваем счетчик попыток)
        await state.update_data(
            conversation_history=conversation_history,
            attempt_count=attempt_count + 1
        )
        
    except Exception as e:
        await async_amplitude_track(
            user_id=message.from_user.id,
            event_type="values_processing_error",
            event_props={"error": str(e)[:100]}  # Ограничиваем длину ошибки
        )
        await message.answer("Произошла ошибка. Попробуйте позже.")
        await state.clear()


@user_router.message(lambda message: message.photo is not None)
async def handle_photo(message: types.Message):
    """Хэндлер для обработки фотографий"""
    try:
        # Получаем файл фотографии (самое высокое качество)
        photo = message.photo[-1]
        file = await message.bot.get_file(photo.file_id)
        
        await async_amplitude_track(
            user_id=message.from_user.id,
            event_type="photo_received"
        )
        
        # Формируем URL файла в Telegram
        file_url = f"https://api.telegram.org/file/bot{settings.BOT_TOKEN}/{file.file_path}"
        
        # Анализируем настроение с помощью OpenAI
        mood_analysis = await analyze_mood(file_url)
        
        # Формируем ответ пользователю
        if "ЛИЦА НЕТ" in mood_analysis:
            await async_amplitude_track(
                user_id=message.from_user.id,
                event_type="no_face_detected"
            )
            await message.answer("😕 Не вижу лица на фото. Попробуй сделать селфи!")
        elif "Ошибка" in mood_analysis:
            await async_amplitude_track(
                user_id=message.from_user.id,
                event_type="mood_analysis_failed"
            )
            await message.answer("⚠️ Что-то пошло не так. Попробуй позже.")
        else:
            await async_amplitude_track(
                user_id=message.from_user.id,
                event_type="mood_analyzed",
                event_props={"mood_result": mood_analysis}
            )
            response_text = f"Я определил твое настроение:\n\n{mood_analysis}"
            audio_response: Optional[BytesIO] = await text_to_audio(response_text, api_key=settings.OPENAI_API_KEY)
            if audio_response:
                audio_response.seek(0)  # Перемещаем указатель в начало
                voice_file = types.BufferedInputFile(
                audio_response.getvalue(), filename="response.ogg"
                )
                await message.answer_voice(voice_file)
            else:
                await message.answer("Ошибка при генерации аудио.")
                  
    except Exception as e:
        await async_amplitude_track(
            user_id=message.from_user.id,
            event_type="photo_processing_error",
            event_props={"error": str(e)}
        )
        await message.answer("🚫 Произошла ошибка при обработке фото.")
        
    
    
    
    
    
    
    
    
    
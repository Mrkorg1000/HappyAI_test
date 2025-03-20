import asyncio
from io import BytesIO
from typing import Optional
from aiogram import Router, types
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram import F, types
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings

from pg_db.database import async_session_maker
from services.audio_to_text_service import audio_to_text
from services.assistant_client_service import get_single_response
from services.check_values_service import save_user_values, user_has_values, validate_values_response
from services.text_to_audio_service import text_to_audio


user_router = Router()


class Form(StatesGroup):
    waiting_for_values = State()


@user_router.message(CommandStart())
async def start(message: types.Message) -> None:
    """
    Обрабатывает команду /start и отправляет приветственное сообщение пользователю.

    Параметры:
    - message (types.Message): Объект сообщения от пользователя.
    """
    await message.answer(
        f"Привет! <b>{message.from_user.first_name}</b>\n"
        "Я отвечу на твои вопросы! Только голосовые!!!",
        parse_mode=ParseMode.HTML
    )


@user_router.message(lambda message: message.text)
async def process_text(message: types.Message) -> None:
    """
    Обрабатывает текстовые сообщения и уведомляет пользователя,
    что бот отвечает только на голосовые сообщения.

    Параметры:
    - message (types.Message): Объект текстового сообщения от пользователя.
    """
    await message.answer(("Общение только голосом!\nИзвини, Брат, такое Задание 😔"))


@user_router.message(lambda message: message.voice, ~StateFilter(Form.waiting_for_values))
async def process_voice_question(message: types.Message, state: FSMContext) -> None:
    """
    Обрабатывает голосовые сообщения: конвертирует их в текст,
    получает ответ от ассистента и отправляет ответ в виде голосового сообщения.

    Параметры:
    - message (types.Message): Объект голосового сообщения от пользователя.
    """
    voice: types.Voice = message.voice
    file_id: str = voice.file_id

    await message.answer("Секундочку, сейчас отвечу")

    # Скачиваем голосовое сообщение
    file: types.File = await message.bot.get_file(file_id)
    downloaded_file: BytesIO = await message.bot.download_file(file.file_path)

    # Преобразуем аудио в текст
    question_text: Optional[str] = await audio_to_text(downloaded_file)

    if question_text is None:
        await message.answer("Не удалось распознать голосовое сообщение.")
        return

    # Получаем ответ от ассистента
    response_text: Optional[str] = await get_single_response(question_text)

    if response_text is None:
        await message.answer("Ошибка при получении ответа от ассистента.")
        return

    # Преобразуем текст ответа в аудио
    audio_response: Optional[BytesIO] = await text_to_audio(response_text, api_key=settings.OPENAI_API_KEY)

    if audio_response:
        audio_response.seek(0)  # Перемещаем указатель в начало
        voice_file = types.BufferedInputFile(
            audio_response.getvalue(), filename="response.ogg"
        )
        await message.answer_voice(voice_file)
    else:
        await message.answer("Ошибка при генерации аудио.")

    await asyncio.sleep(3)
    
    telegram_id = message.from_user.id
    has_values = await user_has_values(telegram_id)
    if not has_values:
        user_name = message.from_user.first_name
        values_question = f"{user_name}, ответь пожалуйста, какие твои жизненные ценности. Можешь назвать несколько."
    
    await state.set_state(Form.waiting_for_values)
    
    audio_response: Optional[BytesIO] = await text_to_audio(values_question, api_key=settings.OPENAI_API_KEY)

    if audio_response:
        audio_response.seek(0)  # Перемещаем указатель в начало
        voice_file = types.BufferedInputFile(
            audio_response.getvalue(), filename="response.ogg"
        )
        await message.answer_voice(voice_file)
        
    else:
        await message.answer("Ошибка при генерации аудио.")
        await state.clear()
        
        
@user_router.message(lambda message: message.voice, StateFilter(Form.waiting_for_values))
async def process_values(
    message: types.Message,
    state: FSMContext,
) -> None:
    """
    Обрабатывает голосовые сообщения от пользователя, которые содержат ответ на вопрос о жизненных ценностях.
    """

    voice: types.Voice = message.voice
    file_id: str = voice.file_id

    await message.answer("Секундочку, сейчас обработаю твои ценности")

    # Скачиваем голосовое сообщение
    file: types.File = await message.bot.get_file(file_id)
    downloaded_file: BytesIO = await message.bot.download_file(file.file_path)

    # Преобразуем аудио в текст
    values_text: Optional[str] = await audio_to_text(downloaded_file)

    if values_text is None:
        await message.answer("Не удалось распознать голосовое сообщение.")
        return

    # Валидируем ответ через OpenAI
    is_valid, values = await validate_values_response(values_text, openai_api_key=settings.OPENAI_API_KEY)

    if not is_valid:
        await message.answer("Ответ невалиден, попробуй еще раз.")
        return

    async with async_session_maker() as session:
        telegram_id = message.from_user.id
        await save_user_values(session, telegram_id, values)
    # Записываем ценности в базу данных
    # telegram_id = message.from_user.id
    # await save_user_values(session, telegram_id, values)

    await message.answer("Ценности успешно сохранены!")
    await state.clear() 
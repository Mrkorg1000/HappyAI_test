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
from services.check_values_service import generate_followup_question, save_user_values, user_has_values, validate_values_response
from services.text_to_audio_service import text_to_audio


user_router = Router()


class Form(StatesGroup):
    waiting_for_values = State()
    refining_values = State()


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
    print('!!!!!!!!!!!!!!!!!!!!!process_text started')
    await message.answer(("Общение только голосом!\nИзвини, Брат, такое Задание 😔"))


@user_router.message(lambda message: message.voice,
                     ~StateFilter(Form.waiting_for_values),
                     ~StateFilter(Form.refining_values)
)
async def process_voice_question(message: types.Message, state: FSMContext) -> None:
    """
    Обрабатывает голосовые сообщения: конвертирует их в текст,
    получает ответ от ассистента и отправляет ответ в виде голосового сообщения.

    Параметры:
    - message (types.Message): Объект голосового сообщения от пользователя.
    """
    print('!!!!!!!!!!!!!!!!!!!!!process_voice_question started')
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

    if is_valid:
        # await message.answer("Ответ невалиден, попробуй еще раз.")
        # return
        async with async_session_maker() as session:
            telegram_id = message.from_user.id
            await save_user_values(session, telegram_id, values)
    # Записываем ценности в базу данных
    # telegram_id = message.from_user.id
    # await save_user_values(session, telegram_id, values)
        await message.answer("Ценности успешно сохранены!")
        await state.clear()
        
    else:
        await state.update_data(previous_responses=[values_text], attempt_count=1)
        
        # Генерируем уточняющий вопрос
        followup_question = await generate_followup_question(
            values_text, 
            attempt=1, 
            openai_api_key=settings.OPENAI_API_KEY
        )
        
        # Переводим в состояние уточнения ценностей
        await state.set_state(Form.refining_values)
        
        audio_response: Optional[BytesIO] = await text_to_audio(followup_question, api_key=settings.OPENAI_API_KEY)
        
        if audio_response:
            audio_response.seek(0)  # Перемещаем указатель в начало
            voice_file = types.BufferedInputFile(
                audio_response.getvalue(), filename="response.ogg"
            )
            await message.answer_voice(voice_file)
        
        else:
            await message.answer("Ошибка при генерации аудио.")
            await state.clear() 
            
            
 # Обработчик для уточняющих голосовых сообщений
@user_router.message(lambda message: message.voice, StateFilter(Form.refining_values))
async def process_values_refinement(
    message: types.Message,
    state: FSMContext,
) -> None:
    """
    Обрабатывает последующие голосовые сообщения для уточнения жизненных ценностей.
    """
    # Получаем данные из состояния
    state_data = await state.get_data()
    previous_responses = state_data.get("previous_responses", [])
    attempt_count = state_data.get("attempt_count", 1)
    
    # Обрабатываем новое голосовое сообщение
    voice: types.Voice = message.voice
    file_id: str = voice.file_id
    
    # Скачиваем голосовое сообщение
    file: types.File = await message.bot.get_file(file_id)
    downloaded_file: BytesIO = await message.bot.download_file(file.file_path)
    
    # Преобразуем аудио в текст
    current_response: Optional[str] = await audio_to_text(downloaded_file)
    if current_response is None:
        await message.answer("Не удалось распознать голосовое сообщение.")
        return
    
    # Добавляем новый ответ к предыдущим
    previous_responses.append(current_response)
    
    # Объединяем все ответы для анализа
    combined_responses = " ".join(previous_responses)
    
    # Валидируем объединенный ответ
    is_valid, values = await validate_values_response(
        combined_responses, 
        openai_api_key=settings.OPENAI_API_KEY
    )
    
    if is_valid:
        # Ценности успешно определены, сохраняем их
        async with async_session_maker() as session:
            telegram_id = message.from_user.id
            await save_user_values(session, telegram_id, values)
        
        # Сообщаем об успехе и очищаем состояние
        await message.answer("Ценности успешно сохранены! Спасибо за твои ответы.")
        await state.clear()
    else:
        # Увеличиваем счетчик попыток
        attempt_count += 1
        
        # Проверяем, не превысили ли максимальное количество попыток
        if attempt_count > 3:  # Максимум 3 попытки уточнения (всего 4 взаимодействия)
            await message.answer("К сожалению, нам не удалось определить твои жизненные ценности. Давай вернемся к этому вопросу позже.")
            await state.clear()
            return
        
        # Генерируем новый уточняющий вопрос
        followup_question = await generate_followup_question(
            combined_responses, 
            attempt=attempt_count, 
            openai_api_key=settings.OPENAI_API_KEY
        )
        
        # Сохраняем обновленную информацию
        await state.update_data(
            previous_responses=previous_responses,
            attempt_count=attempt_count
        )
        
        # Отправляем уточняющий вопрос в аудио формате
        audio_response: Optional[BytesIO] = await text_to_audio(followup_question, api_key=settings.OPENAI_API_KEY)
        if audio_response:
            audio_response.seek(0)
            voice_file = types.BufferedInputFile(
                audio_response.getvalue(), filename="followup_question.ogg"
            )
            await message.answer_voice(voice_file)
        else:
            await message.answer("Ошибка при генерации аудио.")
      

         
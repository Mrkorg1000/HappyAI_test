from io import BytesIO
import json
from typing import Dict, List, Optional, Tuple
import openai
from aiogram import F, types
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from config import settings
from form import Form
from pg_db.database import async_session_maker
from pg_db.models import User, Value
    
    
async def user_has_values(telegram_id: int) -> bool:
    async with async_session_maker() as session:
        stmt = select(User.id).where(User.telegram_id == telegram_id)
        result = await session.execute(stmt)
        return result.scalar() is not None
    
    
async def save_user_values(session: AsyncSession, telegram_id: int, values: list[str]) -> str:
    """
    Сохраняет пользователя и его ценности в базу данных.
    Возвращает JSON-строку с результатом операции.
    Параметры:
    - session (AsyncSession): Асинхронная сессия SQLAlchemy.
    - telegram_id (int): ID пользователя в Telegram.
    - values (list[str]): Список ценностей пользователя.

     Возвращает:
    - str: JSON-строка с {"status": "success/error", "message": "..."}
    """

    try:
        user = User(telegram_id=telegram_id)
        session.add(user)
        await session.flush()  

        # Создаем записи ценностей
        user_values = [Value(user_id=user.id, value=v) for v in values]
        session.add_all(user_values)

        await session.commit()
        return json.dumps({"status": "success", "message": f"Успешно сохранено {len(values)} ценностей."})
    
    except Exception as e:
        await session.rollback()

import json
from typing import List, Tuple
import openai
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pg_db.database import async_session_maker
from pg_db.models import User, Value  
    
    
async def user_has_values(telegram_id: int) -> bool:
    async with async_session_maker() as session:
        stmt = select(User.id).where(User.telegram_id == telegram_id)
        result = await session.execute(stmt)
        return result.scalar() is not None
    
    
async def validate_values_response(response_text: str, openai_api_key: str) -> Tuple[bool, List[str]]:
    """
    Валидирует ответ на вопрос о жизненных ценностях с использованием OpenAI Completions API.
   
    Args:
        response_text (str): Текст ответа пользователя на вопрос "какие твои жизненные ценности"
        openai_api_key (str): Ключ API OpenAI
       
    Returns:
        Tuple[bool, List[str]]: Кортеж из двух элементов:
            - bool: True если ценности определены корректно, False в противном случае
            - List[str]: Список идентифицированных ценностей (пустой список, если ценности не определены)
    """
    # Проверка на пустую строку или очень короткий ответ
    if not response_text or len(response_text.strip()) < 5:
        return False, []
   
    # Отладочный вывод входящего текста
    print(f"DEBUG: Analyzing user response: '{response_text}'")
   
    # Настройка клиента OpenAI
    client = openai.OpenAI(api_key=openai_api_key)
   
    # Создание промпта для API без запроса JSON формата
    prompt = f"""
    Проанализируйте следующий ответ пользователя на вопрос "какие твои жизненные ценности":
   
    ```
    {response_text}
    ```
   
    Оцените, содержит ли этот ответ корректно определенные жизненные ценности.
   
    Ответ считается корректным, если:
    1. Он содержит как минимум одну общепринятую жизненную ценность (например, семья, здоровье, свобода, честность, справедливость, любовь, знания, духовность, и т.д.)
    2. Ценности представлены в понятном контексте
    3. Ответ не содержит бессмысленных или противоречивых утверждений
    4. Ответ не является полностью не относящимся к теме
   
    Ответ считается некорректным, если:
    1. Он состоит из бессмысленного набора слов
    2. Он не содержит упоминания никаких ценностей
    3. Он содержит шутки, оскорбления или неуместный контент
    4. Он полностью не относится к вопросу о ценностях
   
    Извлеките и перечислите все идентифицированные ценности. Ценности должны быть представлены в виде отдельных слов или коротких фраз (например, "семья", "личностный рост").
   
    Верните ответ в следующем формате:
    Первая строка: "VALID" если ответ содержит корректно определенные ценности, или "INVALID" если нет.
    Вторая строка: перечислите все идентифицированные ценности через запятую (только если ответ VALID, иначе оставьте пустую строку).
    """
   
    try:
        # Отправка запроса к API
        completion = client.chat.completions.create(
            model="gpt-4",  # Используйте подходящую модель
            messages=[
                {"role": "system", "content": "Вы - система валидации жизненных ценностей. Ваш ответ должен быть в простом текстовом формате."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )
       
        # Получаем ответ от API
        result = completion.choices[0].message.content
        
        # Отладочный вывод полного ответа API
        print(f"DEBUG: Raw API response: '{result}'")
        
        # Парсим ответ как текст
        lines = result.strip().split("\n")
        print(f"DEBUG: Split into {len(lines)} lines")
        
        if len(lines) < 1:
            print("DEBUG: Response doesn't have enough lines")
            return False, []
        
        # Проверяем валидность
        is_valid = "VALID" in lines[0].upper()
        print(f"DEBUG: First line contains 'VALID': {is_valid}")
        
        values_list = []
        # Если ответ валидный и есть вторая строка, парсим ценности
        if is_valid and len(lines) > 1:
            values_str = lines[1].strip()
            if values_str:
                values_list = [value.strip() for value in values_str.split(",") if value.strip()]
        
        print(f"DEBUG: Extracted values: {values_list}")
        
        # Если ответ отмечен как валидный, но ценности не извлечены, считаем его невалидным
        if is_valid and not values_list:
            print("DEBUG: Response marked as valid but no values identified")
            is_valid = False
        
        return is_valid, values_list
       
    except Exception as e:
        print(f"DEBUG: Error during validation: {e}")
        import traceback
        print(f"DEBUG: Traceback: {traceback.format_exc()}")
        return False, []
    
async def save_user_values(session: AsyncSession, telegram_id: int, values: list[str]) -> None:
    """
    Сохраняет пользователя и его ценности в базу данных.

    Параметры:
    - session (AsyncSession): Асинхронная сессия SQLAlchemy.
    - telegram_id (int): ID пользователя в Telegram.
    - values (list[str]): Список ценностей пользователя.

    """

    # Создаем пользователя
    user = User(telegram_id=telegram_id)
    session.add(user)
    await session.flush()  # Получаем user.id после вставки

    # Создаем записи ценностей
    user_values = [Value(user_id=user.id, value=v) for v in values]
    session.add_all(user_values)

    await session.commit()


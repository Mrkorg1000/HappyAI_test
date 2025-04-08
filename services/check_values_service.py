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
    client = openai.AsyncOpenAI(api_key=openai_api_key)
   
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
        completion = await client.chat.completions.create(
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
    
    
async def generate_followup_question(response_text: str, openai_api_key: str, attempt: int = 1) -> str:
    """
    Генерирует уточняющий вопрос для получения более качественного ответа о жизненных ценностях.
    
    Args:
        response_text (str): Предыдущий ответ пользователя
        attempt (int): Номер попытки (для адаптации подхода)
        openai_api_key (str): Ключ API OpenAI
        
    Returns:
        str: Уточняющий вопрос для пользователя
    """
    client = openai.AsyncOpenAI(api_key=openai_api_key)
    
    # Создаем промпт в зависимости от номера попытки
    if attempt == 1:
        prompt = f"""
        Пользователь ответил на вопрос о жизненных ценностях следующим образом:
        
        ```
        {response_text}
        ```
        
        Этот ответ не содержит четко сформулированных жизненных ценностей. 
        Сформулируй уточняющий вопрос, который поможет пользователю более четко выразить свои жизненные ценности. 
        Вопрос должен быть тактичным, эмпатичным и направляющим.
        
        Важно: ты - голосовой ассистент, твой вопрос будет озвучен, поэтому он должен быть простым для восприятия на слух.
        
        Примеры хороших уточняющих вопросов:
        - "Спасибо за ответ! Давай попробуем немного конкретнее. Что для тебя является самым важным в жизни? Может быть, семья, здоровье, саморазвитие или что-то другое?"
        - "Я хотел бы понять, какие принципы или идеалы направляют твою жизнь. Можешь назвать несколько конкретных ценностей, которые для тебя важны?"
        
        Ответ должен содержать только вопрос без дополнительных пояснений.
        """
    elif attempt == 2:
        prompt = f"""
        Пользователь продолжает отвечать на вопрос о жизненных ценностях. Вот все его ответы до сих пор:
        
        ```
        {response_text}
        ```
        
        Нам все еще не удалось четко определить конкретные жизненные ценности пользователя.
        Сформулируй новый уточняющий вопрос, который поможет пользователю назвать конкретные ценности.
        
        Важно: ты - голосовой ассистент, твой вопрос будет озвучен, поэтому он должен быть простым для восприятия на слух.
        Вопрос должен быть более направляющим, чем предыдущий, возможно с примерами ценностей.
        
        Например: "Давай подумаем о том, что может быть для тебя по-настоящему важно. Это могут быть такие ценности как семья, развитие, свобода, здоровье, дружба, честность или что-то совершенно другое. Какие из этих ценностей отзываются в тебе?"
        
        Ответ должен содержать только вопрос без дополнительных пояснений.
        """
    else:
        prompt = f"""
        Это последняя попытка определить жизненные ценности пользователя. Вот все его ответы до сих пор:
        
        ```
        {response_text}
        ```
        
        Нам по-прежнему не удалось определить конкретные жизненные ценности. 
        Сформулируй максимально прямой и конкретный вопрос, который поможет пользователю назвать свои ценности.
        
        Важно: ты - голосовой ассистент, твой вопрос будет озвучен, поэтому он должен быть простым для восприятия на слух.
        
        Например: "Пожалуйста, просто назови 3-5 самых важных для тебя ценностей в жизни. Например: семья, свобода, честность и т.д."
        
        Ответ должен содержать только вопрос без дополнительных пояснений.
        """
    
    try:
        # Отправка запроса к API
        completion = await client.chat.completions.create(
            model="gpt-4",  # Используйте подходящую модель
            messages=[
                {"role": "system", "content": "Ты - эмпатичный голосовой ассистент, помогающий людям определить их жизненные ценности через наводящие вопросы."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        
        # Получаем и возвращаем сгенерированный вопрос
        return completion.choices[0].message.content.strip()
    except Exception as e:
        print(f"DEBUG: Error generating followup question: {e}")
        # Возвращаем стандартный вопрос в случае ошибки
        fallback_questions = [
            "Мне кажется, мы еще не до конца разобрались с твоими ценностями. Можешь, пожалуйста, назвать несколько конкретных вещей, которые для тебя действительно важны в жизни?",
            "Давай попробуем иначе. Какие принципы или идеалы ты считаешь самыми важными для себя?",
            "Пожалуйста, просто перечисли 3-5 своих главных жизненных ценностей."
        ]
        return fallback_questions[min(attempt - 1, len(fallback_questions) - 1)]


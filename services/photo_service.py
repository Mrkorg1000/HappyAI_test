import openai
from services.assistant_client_service import client


prompt = """
Определи настроение человека на фото и опиши его с лёгким юмором, но без пошлости. 
Если лица нет, ответь 'ЛИЦА НЕТ'. 

Примеры хороших ответов:
- "Настроение: как кот, который только что разбил вазу, но надеется, что никто не заметил"
- "Выглядишь так, будто только выиграл в лотерею, но потерял билет"
- "На лице написано: 'Кофе закончился, а день только начинается'"

Избегай:
- Грубостей и пошлости
- Стереотипов о внешности
- Чрезмерной саркастичности

Ответь одним предложением на русском.
"""


async def analyze_mood(photo_url: str) -> str:
    """Анализ настроения по фото через OpenAI"""
    try:
        response = await client.chat.completions.create(
            model="gpt-4-vision-preview",
            messages=[
                {
                    "role": "user", 
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": photo_url}},
                    ],
                }
            ],
            max_tokens=300,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Ошибка: {str(e)}"
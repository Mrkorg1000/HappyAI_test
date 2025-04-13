import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from aiogram import Bot, Dispatcher
from amplitude import Amplitude
from openai import AsyncOpenAI
from config import settings
from amplitude_dep import amplitude_executor
from handlers.user_handlers import user_router


async def main() -> None:
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(user_router)
    
    try:
        await dp.start_polling(bot)
    finally:
        amplitude_executor.shutdown(wait=True)

if __name__ == "__main__":
    asyncio.run(main())

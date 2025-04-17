import asyncio
import redis.asyncio as redis
from aiogram.fsm.storage.redis import RedisStorage
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from aiogram import Bot, Dispatcher
from amplitude import Amplitude
from openai import AsyncOpenAI
from config import settings
from amplitude_dep import amplitude_executor
from handlers.user_handlers import user_router


async def main() -> None:
    redis_connection = redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD,
        decode_responses=True
    )
    
    storage = RedisStorage(redis_connection)
    
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher(storage=storage)
    dp.include_router(user_router)
    
    try:
        await dp.start_polling(bot)
    finally:
        await redis_connection.close() 
        amplitude_executor.shutdown(wait=True)

if __name__ == "__main__":
    asyncio.run(main())

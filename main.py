import asyncio
from aiogram import Bot, Dispatcher
from config import settings
from handlers.user_handlers import user_router


async def main() -> None:
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(user_router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

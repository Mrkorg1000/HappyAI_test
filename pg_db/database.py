from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from config import settings


engine = create_async_engine(settings.database_url, echo=True)


async_session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


# async def get_session():
#     async with async_session_maker() as session:
#         yield session
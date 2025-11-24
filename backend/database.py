from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from backend.models import Base
from backend.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_session() -> AsyncSession:
    async with async_session_maker() as session:
        yield session

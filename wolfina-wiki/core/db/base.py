from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from core.settings import settings

engine = create_async_engine(settings.database_url, echo=settings.debug, future=True)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


# Import all models here so alembic autogenerate can discover them.
def import_models() -> None:  # noqa: F401
    import core.models.page  # noqa: F401
    import core.models.proposal  # noqa: F401
    import core.models.plugin  # noqa: F401

import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.auth.deps import create_access_token
from src.database import get_db
from src.main import app
from src.models.base import Base
from src.models.user import User, UserRole

TEST_DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://pgdlibre:pgdlibre@localhost:5432/pgdlibre",
)


async def persist_user(
    db: AsyncSession,
    *,
    email: str,
    name: str = "",
    role: UserRole = UserRole.SERVIDOR,
    is_active: bool = True,
) -> User:
    user = User(
        email=email, name=name or email.split("@")[0], role=role, is_active=is_active
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def set_auth_cookie(client: AsyncClient, user: User) -> None:
    client.cookies.set("access_token", create_access_token(user))


@pytest.fixture
async def db():
    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session
        await session.rollback()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def client(db: AsyncSession):
    async def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c
    app.dependency_overrides.clear()

import strawberry
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from strawberry.fastapi import GraphQLRouter
from strawberry.types import Info

from ..auth.deps import get_optional_user
from ..database import get_db
from ..models.user import User


@strawberry.type
class UserType:
    id: int
    email: str
    name: str
    role: str


@strawberry.type
class Query:
    @strawberry.field
    def health(self) -> str:
        return "ok"

    @strawberry.field
    def me(self, info: Info) -> UserType | None:
        user: User | None = info.context.get("user")
        if not user:
            return None
        return UserType(
            id=user.id, email=user.email, name=user.name, role=user.role.value
        )


async def get_context(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> dict:
    return {"request": request, "db": db, "user": user}


schema = strawberry.Schema(query=Query)
graphql_router = GraphQLRouter(schema, context_getter=get_context)

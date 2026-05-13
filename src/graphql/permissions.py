from typing import Any

from strawberry.permission import BasePermission
from strawberry.types import Info

from ..models.user import User, UserRole


class IsAuthenticated(BasePermission):
    message = "Autenticação necessária"

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        return info.context.get("user") is not None


class IsAdmin(BasePermission):
    message = "Perfil ADMIN necessário"

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        user: User | None = info.context.get("user")
        return user is not None and user.role == UserRole.ADMIN


class IsGestorOrAdmin(BasePermission):
    message = "Perfil GESTOR_UNIDADE ou ADMIN necessário"

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        user: User | None = info.context.get("user")
        return user is not None and user.role in (
            UserRole.ADMIN,
            UserRole.GESTOR_UNIDADE,
        )


class IsChefiaOrAbove(BasePermission):
    message = "Perfil CHEFE_IMEDIATO, GESTOR_UNIDADE ou ADMIN necessário"

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        user: User | None = info.context.get("user")
        return user is not None and user.role in (
            UserRole.ADMIN,
            UserRole.GESTOR_UNIDADE,
            UserRole.CHEFE_IMEDIATO,
        )

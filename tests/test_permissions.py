"""Testes unitários para src/graphql/permissions.py — sem I/O."""
from src.graphql.permissions import (
    IsAdmin,
    IsAuthenticated,
    IsChefiaOrAbove,
    IsGestorOrAdmin,
)
from src.models.user import User, UserRole


class _Info:
    """Stub mínimo de strawberry.types.Info para testes unitários."""

    def __init__(self, user: User | None = None) -> None:
        self.context: dict = {"user": user}


def _user(role: UserRole) -> User:
    return User(id=1, email="u@u.br", name="U", role=role)


# ---------------------------------------------------------------------------
# TC-M06-007  IsAuthenticated
# ---------------------------------------------------------------------------

def test_is_authenticated_blocks_anonymous() -> None:
    assert not IsAuthenticated().has_permission(None, _Info())


def test_is_authenticated_allows_servidor() -> None:
    assert IsAuthenticated().has_permission(None, _Info(_user(UserRole.SERVIDOR)))


def test_is_authenticated_allows_admin() -> None:
    assert IsAuthenticated().has_permission(None, _Info(_user(UserRole.ADMIN)))


# ---------------------------------------------------------------------------
# TC-M06-007  IsAdmin
# ---------------------------------------------------------------------------

def test_is_admin_blocks_anonymous() -> None:
    assert not IsAdmin().has_permission(None, _Info())


def test_is_admin_blocks_servidor() -> None:
    assert not IsAdmin().has_permission(None, _Info(_user(UserRole.SERVIDOR)))


def test_is_admin_blocks_chefe() -> None:
    assert not IsAdmin().has_permission(None, _Info(_user(UserRole.CHEFE_IMEDIATO)))


def test_is_admin_blocks_gestor() -> None:
    assert not IsAdmin().has_permission(None, _Info(_user(UserRole.GESTOR_UNIDADE)))


def test_is_admin_allows_admin() -> None:
    assert IsAdmin().has_permission(None, _Info(_user(UserRole.ADMIN)))


# ---------------------------------------------------------------------------
# TC-M06-008  IsGestorOrAdmin
# ---------------------------------------------------------------------------

def test_is_gestor_or_admin_blocks_anonymous() -> None:
    assert not IsGestorOrAdmin().has_permission(None, _Info())


def test_is_gestor_or_admin_blocks_servidor() -> None:
    assert not IsGestorOrAdmin().has_permission(None, _Info(_user(UserRole.SERVIDOR)))


def test_is_gestor_or_admin_blocks_chefe() -> None:
    assert not IsGestorOrAdmin().has_permission(
        None, _Info(_user(UserRole.CHEFE_IMEDIATO))
    )


def test_is_gestor_or_admin_allows_gestor() -> None:
    assert IsGestorOrAdmin().has_permission(None, _Info(_user(UserRole.GESTOR_UNIDADE)))


def test_is_gestor_or_admin_allows_admin() -> None:
    assert IsGestorOrAdmin().has_permission(None, _Info(_user(UserRole.ADMIN)))


# ---------------------------------------------------------------------------
# TC-M06-009  IsChefiaOrAbove
# ---------------------------------------------------------------------------

def test_is_chefia_or_above_blocks_anonymous() -> None:
    assert not IsChefiaOrAbove().has_permission(None, _Info())


def test_is_chefia_or_above_blocks_servidor() -> None:
    assert not IsChefiaOrAbove().has_permission(None, _Info(_user(UserRole.SERVIDOR)))


def test_is_chefia_or_above_allows_chefe() -> None:
    assert IsChefiaOrAbove().has_permission(None, _Info(_user(UserRole.CHEFE_IMEDIATO)))


def test_is_chefia_or_above_allows_gestor() -> None:
    assert IsChefiaOrAbove().has_permission(None, _Info(_user(UserRole.GESTOR_UNIDADE)))


def test_is_chefia_or_above_allows_admin() -> None:
    assert IsChefiaOrAbove().has_permission(None, _Info(_user(UserRole.ADMIN)))

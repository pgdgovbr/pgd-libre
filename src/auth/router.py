from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database import get_db
from ..models.user import User, UserRole
from .deps import create_access_token, get_optional_user
from .oauth import oauth

router = APIRouter()

_COOKIE_NAME = "access_token"
_COOKIE_MAX_AGE = 60 * 60 * 8  # 8 horas


@router.get("/providers")
async def list_providers() -> list[dict]:
    """Retorna providers configurados — mesmo padrão do NextAuth /api/auth/providers."""
    settings = get_settings()
    providers = []
    if settings.GOOGLE_CLIENT_ID:
        providers.append({"id": "google", "name": "Google"})
    if settings.GOVBR_CLIENT_ID:
        providers.append({"id": "govbr", "name": "Gov.Br"})
    return providers


@router.get("/login/{provider}")
async def login(request: Request, provider: str) -> RedirectResponse:
    client = oauth.create_client(provider)
    if client is None:
        raise HTTPException(status_code=404, detail=f"Provider '{provider}' não configurado")
    redirect_uri = str(request.url_for("oauth_callback", provider=provider))
    return await client.authorize_redirect(request, redirect_uri)


@router.get("/callback/{provider}", name="oauth_callback")
async def callback(
    request: Request,
    provider: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    client = oauth.create_client(provider)
    if client is None:
        raise HTTPException(status_code=404, detail=f"Provider '{provider}' não configurado")

    try:
        token = await client.authorize_access_token(request)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Erro OAuth: {exc}") from exc

    user_info = token.get("userinfo") or {}
    email = user_info.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Provider não retornou e-mail")

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            email=email,
            name=user_info.get("name") or email.split("@")[0],
            role=UserRole.SERVIDOR,
            oauth_sub=user_info.get("sub"),
            oauth_provider=provider,
        )
        db.add(user)
    else:
        user.oauth_sub = user_info.get("sub") or user.oauth_sub
        user.oauth_provider = provider
        if user_info.get("name"):
            user.name = user_info["name"]

    user.last_login_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(user)

    settings = get_settings()
    access_token = create_access_token(user)

    # O token vai como query param para que o frontend (domínio diferente) possa
    # lê-lo e setar seu próprio cookie httpOnly — cookies cross-domain não funcionam
    # entre *.a.run.app subdomains distintos.
    redirect_url = f"{settings.FRONTEND_URL}?token={access_token}"
    return RedirectResponse(url=redirect_url)


@router.get("/me")
async def me(user: User | None = Depends(get_optional_user)) -> dict:
    if not user:
        raise HTTPException(status_code=401, detail="Não autenticado")
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
    }


@router.post("/logout")
async def logout(response: Response) -> dict:
    response.delete_cookie(_COOKIE_NAME)
    return {"ok": True}


@router.post("/dev-login")
async def dev_login(
    email: str,
    name: str = "",
    role: str = "servidor",
    response: Response = None,  # type: ignore[assignment]
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Cria/recupera usuário e define cookie — apenas fora de production.
    Usado exclusivamente pelos testes automatizados (Playwright global-setup).
    """
    if get_settings().ENVIRONMENT == "production":
        raise HTTPException(status_code=403, detail="Não disponível em produção")

    try:
        user_role = UserRole(role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Role inválida: {role}") from None

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            email=email,
            name=name or email.split("@")[0],
            role=user_role,
        )
        db.add(user)
    else:
        user.role = user_role
        if name:
            user.name = name

    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(user)
    response.set_cookie(
        key=_COOKIE_NAME,
        value=access_token,
        max_age=_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=False,
    )
    return {
        "ok": True,
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "token": access_token,
    }

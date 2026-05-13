from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from .api.health import router as health_router
from .auth.router import router as auth_router
from .config import get_settings
from .graphql.schema import graphql_router


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="PGD Libre",
        description="Plataforma de Gestão e Desempenho — instalação no órgão",
        version="0.1.0",
        docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
        redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
    )

    # SessionMiddleware é necessário para o OAuth CSRF state (authlib Starlette)
    app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_URL],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rejeita requisições sem User-Agent (padrão api-pgd)
    @app.middleware("http")
    async def require_user_agent(request: Request, call_next):  # type: ignore[no-untyped-def]
        if not request.headers.get("user-agent"):
            return JSONResponse(
                status_code=400,
                content={"detail": "User-Agent header obrigatório"},
            )
        return await call_next(request)

    app.include_router(health_router, tags=["infra"])
    app.include_router(auth_router, prefix="/auth", tags=["auth"])
    app.include_router(graphql_router, prefix="/graphql")

    return app


app = create_app()

from authlib.integrations.starlette_client import OAuth

from ..config import get_settings


def _build_oauth() -> OAuth:
    settings = get_settings()
    o = OAuth()

    # Google OAuth — desenvolvimento (padrão DGB)
    if settings.GOOGLE_CLIENT_ID:
        o.register(
            name="google",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )

    # Gov.br OIDC — produção
    if settings.GOVBR_CLIENT_ID:
        o.register(
            name="govbr",
            client_id=settings.GOVBR_CLIENT_ID,
            client_secret=settings.GOVBR_CLIENT_SECRET,
            server_metadata_url=f"{settings.GOVBR_ISSUER}/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )

    return o


oauth = _build_oauth()

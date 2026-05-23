from typing import Annotated

from fastapi import Header, HTTPException, WebSocket, status

from manfriday.config.settings import Settings


def _is_valid_bearer(authorization: str | None, settings: Settings) -> bool:
    if authorization is None:
        return False
    scheme, separator, token = authorization.partition(" ")
    if separator == "" or scheme.lower() != "bearer" or token == "":
        return False
    return token == settings.local_secret.get_secret_value()


async def require_auth(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    # The dependency is bound to app settings in create_app().
    raise RuntimeError("require_auth must be overridden by create_app")


def build_auth_dependency(settings: Settings):
    async def dependency(authorization: Annotated[str | None, Header()] = None) -> None:
        if not _is_valid_bearer(authorization, settings):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": {
                        "code": "unauthorized",
                        "message": "Missing or invalid bearer token.",
                        "retryable": False,
                    },
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

    return dependency


def websocket_authorized(websocket: WebSocket, settings: Settings) -> bool:
    return _is_valid_bearer(websocket.headers.get("authorization"), settings)

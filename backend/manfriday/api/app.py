from datetime import UTC, datetime

from fastapi import FastAPI

from manfriday import __version__
from manfriday.config.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    app = FastAPI(
        title="Man Friday Backend",
        version=__version__,
        docs_url="/docs" if app_settings.env != "production" else None,
        redoc_url=None,
    )

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "manfriday-backend",
            "version": __version__,
            "time": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }

    return app

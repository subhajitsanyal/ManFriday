import uvicorn

from manfriday.config.settings import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "manfriday.api.app:create_app",
        host=settings.host,
        port=settings.port,
        reload=settings.env == "local",
        factory=True,
    )


if __name__ == "__main__":
    main()

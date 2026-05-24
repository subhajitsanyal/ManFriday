from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from manfriday.config.settings import Settings
from manfriday.gopro.models import GoProState


@dataclass(frozen=True)
class GoProControllerStatus:
    status: GoProState
    camera_identifier: str
    message: str | None = None


class GoProController(Protocol):
    def status(self) -> GoProControllerStatus: ...

    def start_preview(self) -> GoProControllerStatus: ...

    def stop_preview(self) -> GoProControllerStatus: ...

    def clear_saved_credentials(self) -> None: ...


class FixtureGoProController:
    def __init__(self, *, settings: Settings) -> None:
        self._camera_identifier = settings.gopro_serial_suffix
        self._credentials_path = settings.gopro_cohn_credentials_path
        self._preview_running = False

    def status(self) -> GoProControllerStatus:
        return GoProControllerStatus(
            status=GoProState.PREVIEW_RUNNING
            if self._preview_running
            else GoProState.PREVIEW_STOPPED,
            camera_identifier=self._camera_identifier,
            message=None if self._preview_running else "Preview is stopped.",
        )

    def start_preview(self) -> GoProControllerStatus:
        self._preview_running = True
        return self.status()

    def stop_preview(self) -> GoProControllerStatus:
        self._preview_running = False
        return self.status()

    def clear_saved_credentials(self) -> None:
        self._preview_running = False
        _clear_file(self._credentials_path)


class OpenGoProController:
    def __init__(self, *, settings: Settings) -> None:
        self._camera_identifier = settings.gopro_serial_suffix
        self._credentials_path = settings.gopro_cohn_credentials_path

    def status(self) -> GoProControllerStatus:
        if not self._credentials_path.exists():
            return GoProControllerStatus(
                status=GoProState.CREDENTIALS_MISSING,
                camera_identifier=self._camera_identifier,
                message="Saved GoPro COHN credentials were not found.",
            )
        return GoProControllerStatus(
            status=GoProState.CONNECTED,
            camera_identifier=self._camera_identifier,
            message="Saved GoPro COHN credentials found. Hardware connection is pending.",
        )

    def start_preview(self) -> GoProControllerStatus:
        if not self._credentials_path.exists():
            return GoProControllerStatus(
                status=GoProState.RECONFIGURE_REQUIRED,
                camera_identifier=self._camera_identifier,
                message="GoPro reconfigure is required before preview can start.",
            )
        return GoProControllerStatus(
            status=GoProState.CONNECTED,
            camera_identifier=self._camera_identifier,
            message="Open GoPro preview start is not implemented yet.",
        )

    def stop_preview(self) -> GoProControllerStatus:
        return self.status()

    def clear_saved_credentials(self) -> None:
        _clear_file(self._credentials_path)


def build_gopro_controller(settings: Settings) -> GoProController:
    if settings.gopro_controller == "open_gopro":
        return OpenGoProController(settings=settings)
    return FixtureGoProController(settings=settings)


def _clear_file(path: Path) -> None:
    if path.exists():
        path.unlink()

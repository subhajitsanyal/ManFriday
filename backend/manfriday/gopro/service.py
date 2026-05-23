from datetime import UTC, datetime

from manfriday.config.settings import Settings
from manfriday.frames import FrameStore
from manfriday.gopro.models import GoProState, GoProStatus, VisualState


class GoProService:
    def __init__(self, *, settings: Settings, frame_store: FrameStore) -> None:
        self._settings = settings
        self._frame_store = frame_store
        self._preview_running = False

    def get_status(self) -> GoProStatus:
        latest = self._frame_store.latest()
        if self._preview_running:
            visual_status = (
                VisualState.HEALTHY
                if self._frame_store.latest_if_healthy()
                else VisualState.DEGRADED
            )
            message = (
                None
                if visual_status == VisualState.HEALTHY
                else "No fresh frame is available."
            )
            return GoProStatus(
                status=GoProState.PREVIEW_RUNNING,
                camera_identifier=self._settings.gopro_serial_suffix,
                preview_running=True,
                visual_status=visual_status,
                last_frame_at=latest.captured_at if latest else None,
                message=message,
            )
        return GoProStatus(
            status=GoProState.PREVIEW_STOPPED,
            camera_identifier=self._settings.gopro_serial_suffix,
            preview_running=False,
            visual_status=VisualState.UNAVAILABLE if latest is None else VisualState.DEGRADED,
            last_frame_at=latest.captured_at if latest else None,
            message="Preview is stopped.",
        )

    def start_preview(self) -> GoProStatus:
        self._preview_running = True
        self._frame_store.seed_fixture_frame(datetime.now(UTC))
        return self.get_status()

    def stop_preview(self) -> GoProStatus:
        self._preview_running = False
        return self.get_status()

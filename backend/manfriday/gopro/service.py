from datetime import UTC, datetime
from time import sleep
from uuid import uuid4

from manfriday.config.settings import Settings
from manfriday.frames import (
    FfmpegFrameSampler,
    FixtureFrameSampler,
    FrameSampler,
    FrameSamplerState,
    FrameStore,
)
from manfriday.gopro.controller import FixtureGoProController, GoProController
from manfriday.gopro.models import (
    GoProReconfigureState,
    GoProReconfigureStatus,
    GoProState,
    GoProStatus,
    VisualState,
)


class GoProService:
    def __init__(
        self,
        *,
        settings: Settings,
        frame_store: FrameStore,
        controller: GoProController | None = None,
    ) -> None:
        self._settings = settings
        self._frame_store = frame_store
        self._controller = controller or FixtureGoProController(settings=settings)
        self._sampler = self._build_sampler()
        self._preview_running = False
        self._reconfigure_status = GoProReconfigureStatus(status=GoProReconfigureState.IDLE)

    def get_status(self) -> GoProStatus:
        latest = self._frame_store.latest()
        sampler_status = self._sampler.status()
        if sampler_status.state == FrameSamplerState.FAILED:
            return GoProStatus(
                status=GoProState.DEGRADED,
                camera_identifier=self._controller.status().camera_identifier,
                preview_running=False,
                visual_status=VisualState.DEGRADED,
                last_frame_at=latest.captured_at if latest else None,
                message=sampler_status.message,
            )
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
                camera_identifier=self._controller.status().camera_identifier,
                preview_running=True,
                visual_status=visual_status,
                last_frame_at=latest.captured_at if latest else None,
                message=message,
            )
        controller_status = self._controller.status()
        if controller_status.status not in {
            GoProState.PREVIEW_STOPPED,
            GoProState.PREVIEW_RUNNING,
        }:
            return GoProStatus(
                status=controller_status.status,
                camera_identifier=controller_status.camera_identifier,
                preview_running=False,
                visual_status=VisualState.UNAVAILABLE,
                last_frame_at=latest.captured_at if latest else None,
                message=controller_status.message,
            )
        return GoProStatus(
            status=controller_status.status,
            camera_identifier=controller_status.camera_identifier,
            preview_running=False,
            visual_status=VisualState.UNAVAILABLE if latest is None else VisualState.DEGRADED,
            last_frame_at=latest.captured_at if latest else None,
            message=controller_status.message,
        )

    def start_preview(self) -> GoProStatus:
        controller_status = self._controller.start_preview()
        self._preview_running = controller_status.status == GoProState.PREVIEW_RUNNING
        if self._preview_running:
            self._sampler.start(datetime.now(UTC))
            self._wait_for_first_frame()
            return self.get_status()
        latest = self._frame_store.latest()
        return GoProStatus(
            status=controller_status.status,
            camera_identifier=controller_status.camera_identifier,
            preview_running=False,
            visual_status=VisualState.UNAVAILABLE,
            last_frame_at=latest.captured_at if latest else None,
            message=controller_status.message,
        )

    def stop_preview(self) -> GoProStatus:
        self._controller.stop_preview()
        self._preview_running = False
        self._sampler.stop()
        return self.get_status()

    def preview_running(self) -> bool:
        return self._preview_running

    def reconfigure(self) -> GoProReconfigureStatus:
        self.stop_preview()
        self._controller.clear_saved_credentials()
        self._reconfigure_status = GoProReconfigureStatus(
            status=GoProReconfigureState.STARTED,
            job_id=f"gopro_reconfigure_{uuid4().hex}",
            started_at=datetime.now(UTC),
            message="Saved GoPro credentials cleared. Hardware provisioning is pending.",
        )
        return self._reconfigure_status

    def cancel_reconfigure(self) -> GoProReconfigureStatus:
        current = self._reconfigure_status
        if current.status == GoProReconfigureState.STARTED:
            self._reconfigure_status = GoProReconfigureStatus(
                status=GoProReconfigureState.CANCELLED,
                job_id=current.job_id,
                started_at=current.started_at,
                message="GoPro reconfigure cancelled.",
            )
        return self._reconfigure_status

    def sampler(self) -> FrameSampler:
        return self._sampler

    def _build_sampler(self) -> FrameSampler:
        if (
            self._settings.gopro_controller == "open_gopro"
            and self._settings.gopro_allow_external_udp_stream
        ):
            return FfmpegFrameSampler(
                frame_store=self._frame_store,
                stream_url=self._settings.frame_udp_url,
                ffmpeg_path=self._settings.ffmpeg_path,
                fps=self._settings.frame_sample_fps,
                jpeg_quality=self._settings.frame_jpeg_quality,
            )
        return FixtureFrameSampler(frame_store=self._frame_store)

    def _wait_for_first_frame(self) -> None:
        if self._frame_store.latest_if_healthy() is not None:
            return
        for _ in range(50):
            sleep(0.1)
            if self._frame_store.latest_if_healthy() is not None:
                return

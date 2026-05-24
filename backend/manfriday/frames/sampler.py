from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from manfriday.frames.models import FrameMetadata
from manfriday.frames.store import FrameStore


class FrameSamplerState(StrEnum):
    STOPPED = "stopped"
    RUNNING = "running"
    FAILED = "failed"


@dataclass(frozen=True)
class FrameSamplerStatus:
    state: FrameSamplerState
    last_sampled_at: datetime | None = None
    message: str | None = None


class FixtureFrameSampler:
    """Deterministic sampler used until the real ffmpeg sampler lands."""

    def __init__(self, *, frame_store: FrameStore) -> None:
        self._frame_store = frame_store
        self._running = False
        self._failed_message: str | None = None
        self._last_sampled_at: datetime | None = None

    def start(self, now: datetime | None = None) -> FrameMetadata:
        if self._running:
            latest = self._frame_store.latest()
            if latest is not None:
                return latest
        self._running = True
        self._failed_message = None
        return self.sample(now)

    def sample(self, now: datetime | None = None) -> FrameMetadata:
        if not self._running:
            self._running = True
        captured_at = now or datetime.now(UTC)
        frame = self._frame_store.seed_fixture_frame(captured_at)
        self._last_sampled_at = captured_at
        return frame

    def stop(self) -> None:
        self._running = False

    def mark_failed(self, message: str) -> None:
        self._running = False
        self._failed_message = message

    def status(self) -> FrameSamplerStatus:
        if self._failed_message is not None:
            return FrameSamplerStatus(
                state=FrameSamplerState.FAILED,
                last_sampled_at=self._last_sampled_at,
                message=self._failed_message,
            )
        if self._running:
            return FrameSamplerStatus(
                state=FrameSamplerState.RUNNING,
                last_sampled_at=self._last_sampled_at,
            )
        return FrameSamplerStatus(
            state=FrameSamplerState.STOPPED,
            last_sampled_at=self._last_sampled_at,
        )

import base64
from datetime import UTC, datetime, timedelta

from manfriday.frames.models import FrameMetadata, FrameSource

FIXTURE_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////"
    "2wBDAf//////////////////////////////////////////////////////////////////////////////////////"
    "wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIQAxAAAAH/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAEFAqf/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAEDAQE/ASP/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAECAQE/ASP/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAY/Al//xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAE/IV//2gAMAwEAAgADAAAAEP/EFBQRAQAAAAAAAAAAAAAAAAAAABD/2gAIAQMBAT8QH//EFBQRAQAAAAAAAAAAAAAAAAAAABD/2gAIAQIBAT8QH//EFBABAQAAAAAAAAAAAAAAAAAAABD/2gAIAQEAAT8QH//Z",
)


class FrameStore:
    def __init__(self, *, look_ttl_seconds: int, stale_after_seconds: int) -> None:
        self._look_ttl = timedelta(seconds=look_ttl_seconds)
        self._stale_after = timedelta(seconds=stale_after_seconds)
        self._latest: FrameMetadata | None = None
        self._pinned: FrameMetadata | None = None
        self._frames: dict[str, FrameMetadata] = {}

    def seed_fixture_frame(self, now: datetime | None = None) -> FrameMetadata:
        captured_at = now or datetime.now(UTC)
        frame = FrameMetadata(
            frame_id=frame_id(captured_at),
            captured_at=captured_at,
            width=1,
            height=1,
            jpeg_bytes=FIXTURE_JPEG,
            source=FrameSource.FIXTURE,
        )
        self._latest = frame
        self._frames[frame.frame_id] = frame
        return frame

    def latest(self) -> FrameMetadata | None:
        return self._latest

    def latest_if_healthy(self, now: datetime | None = None) -> FrameMetadata | None:
        latest = self._latest
        if latest is None:
            return None
        current = now or datetime.now(UTC)
        if current - latest.captured_at > self._stale_after:
            return None
        return latest

    def pin_latest(self, now: datetime | None = None) -> FrameMetadata | None:
        current = now or datetime.now(UTC)
        latest = self.latest_if_healthy(current)
        if latest is None:
            return None
        pinned = latest.model_copy(
            update={
                "is_pinned": True,
                "pin_expires_at": current + self._look_ttl,
                "source": FrameSource.LOOK,
            },
        )
        self._pinned = pinned
        self._frames[pinned.frame_id] = pinned
        return pinned

    def pinned(self, now: datetime | None = None) -> FrameMetadata | None:
        pinned = self._pinned
        if pinned is None:
            return None
        current = now or datetime.now(UTC)
        if pinned.pin_expires_at is not None and pinned.pin_expires_at <= current:
            self._pinned = None
            return None
        return pinned

    def get(self, frame_id: str) -> FrameMetadata | None:
        return self._frames.get(frame_id)

    def clear_pin(self) -> None:
        self._pinned = None


def frame_id(captured_at: datetime) -> str:
    return f"frame_{captured_at.strftime('%Y_%m_%dT%H_%M_%S_%fZ')}"

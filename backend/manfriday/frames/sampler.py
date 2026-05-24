import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from threading import Event, Lock, Thread
from typing import Protocol

from manfriday.frames.models import FrameMetadata, FrameSource
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


class FrameSampler(Protocol):
    def start(self, now: datetime | None = None) -> FrameMetadata | None: ...

    def stop(self) -> None: ...

    def status(self) -> FrameSamplerStatus: ...


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


class FfmpegFrameSampler:
    """Samples JPEG frames from a UDP/video stream using a long-running ffmpeg process."""

    def __init__(
        self,
        *,
        frame_store: FrameStore,
        stream_url: str,
        ffmpeg_path: str,
        fps: int,
        jpeg_quality: int,
        popen_factory=subprocess.Popen,
    ) -> None:
        self._frame_store = frame_store
        self._stream_url = stream_url
        self._ffmpeg_path = ffmpeg_path
        self._fps = max(1, fps)
        self._jpeg_quality = min(max(2, jpeg_quality), 31)
        self._popen_factory = popen_factory
        self._stop_event = Event()
        self._lock = Lock()
        self._thread: Thread | None = None
        self._process: subprocess.Popen | None = None
        self._last_sampled_at: datetime | None = None
        self._failed_message: str | None = None

    def start(self, now: datetime | None = None) -> FrameMetadata | None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self._frame_store.latest()
            self._stop_event.clear()
            self._failed_message = None
            self._thread = Thread(target=self._run, name="ffmpeg-frame-sampler", daemon=True)
            self._thread.start()
            return self._frame_store.latest()

    def stop(self) -> None:
        self._stop_event.set()
        process = self._process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2)

    def status(self) -> FrameSamplerStatus:
        with self._lock:
            if self._failed_message is not None:
                return FrameSamplerStatus(
                    state=FrameSamplerState.FAILED,
                    last_sampled_at=self._last_sampled_at,
                    message=self._failed_message,
                )
            if self._thread is not None and self._thread.is_alive():
                return FrameSamplerStatus(
                    state=FrameSamplerState.RUNNING,
                    last_sampled_at=self._last_sampled_at,
                )
            return FrameSamplerStatus(
                state=FrameSamplerState.STOPPED,
                last_sampled_at=self._last_sampled_at,
            )

    def command(self) -> list[str]:
        return [
            self._ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "warning",
            "-fflags",
            "nobuffer",
            "-flags",
            "low_delay",
            "-i",
            self._stream_url,
            "-an",
            "-vf",
            f"fps={self._fps}",
            "-q:v",
            str(self._jpeg_quality),
            "-f",
            "image2pipe",
            "-vcodec",
            "mjpeg",
            "pipe:1",
        ]

    def _run(self) -> None:
        try:
            process = self._popen_factory(
                self.command(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self._process = process
            self._read_jpegs(process)
            return_code = process.poll()
            if not self._stop_event.is_set() and return_code not in {None, 0}:
                self._mark_failed(f"ffmpeg exited with status {return_code}.")
        except Exception as exc:
            self._mark_failed(f"ffmpeg sampler failed: {exc}")
        finally:
            self._process = None

    def _read_jpegs(self, process: subprocess.Popen) -> None:
        assert process.stdout is not None
        buffer = b""
        while not self._stop_event.is_set():
            chunk = process.stdout.read(8192)
            if not chunk:
                if process.poll() is not None:
                    break
                continue
            buffer += chunk
            while True:
                start = buffer.find(b"\xff\xd8")
                if start < 0:
                    buffer = buffer[-1:]
                    break
                end = buffer.find(b"\xff\xd9", start + 2)
                if end < 0:
                    buffer = buffer[start:]
                    break
                jpeg = buffer[start : end + 2]
                buffer = buffer[end + 2 :]
                self._store_jpeg(jpeg)

    def _store_jpeg(self, jpeg: bytes) -> None:
        captured_at = datetime.now(UTC)
        width, height = _jpeg_dimensions(jpeg)
        frame = FrameMetadata(
            frame_id=_frame_id(captured_at),
            captured_at=captured_at,
            width=width,
            height=height,
            jpeg_bytes=jpeg,
            source=FrameSource.LATEST,
        )
        self._frame_store.put(frame)
        with self._lock:
            self._last_sampled_at = captured_at

    def _mark_failed(self, message: str) -> None:
        with self._lock:
            self._failed_message = message


def _frame_id(captured_at: datetime) -> str:
    return "frame_" + captured_at.isoformat().replace("+00:00", "Z").replace(":", "_")


def _jpeg_dimensions(jpeg: bytes) -> tuple[int, int]:
    index = 2
    while index + 9 < len(jpeg):
        if jpeg[index] != 0xFF:
            index += 1
            continue
        marker = jpeg[index + 1]
        index += 2
        if marker in {0xD8, 0xD9}:
            continue
        if index + 2 > len(jpeg):
            break
        length = int.from_bytes(jpeg[index : index + 2], "big")
        if length < 2 or index + length > len(jpeg):
            break
        if marker in {
            0xC0,
            0xC1,
            0xC2,
            0xC3,
            0xC5,
            0xC6,
            0xC7,
            0xC9,
            0xCA,
            0xCB,
            0xCD,
            0xCE,
            0xCF,
        }:
            height = int.from_bytes(jpeg[index + 3 : index + 5], "big")
            width = int.from_bytes(jpeg[index + 5 : index + 7], "big")
            return width, height
        index += length
    return 0, 0

from time import sleep

from manfriday.frames import FfmpegFrameSampler, FrameSamplerState, FrameStore
from manfriday.frames.models import FrameSource
from manfriday.frames.store import FIXTURE_JPEG


def test_ffmpeg_sampler_builds_udp_jpeg_pipe_command() -> None:
    store = _frame_store()
    sampler = FfmpegFrameSampler(
        frame_store=store,
        stream_url="udp://@:8554",
        ffmpeg_path="/opt/homebrew/bin/ffmpeg",
        fps=2,
        jpeg_quality=80,
    )

    command = sampler.command()

    assert command[0] == "/opt/homebrew/bin/ffmpeg"
    assert "udp://@:8554" in command
    assert "fps=2" in command
    assert "31" in command
    assert command[-3:] == ["-vcodec", "mjpeg", "pipe:1"]


def test_ffmpeg_sampler_ingests_jpeg_from_stdout() -> None:
    store = _frame_store()
    process = _FakeProcess(stdout_chunks=[FIXTURE_JPEG], return_code=0)
    sampler = FfmpegFrameSampler(
        frame_store=store,
        stream_url="udp://@:8554",
        ffmpeg_path="ffmpeg",
        fps=2,
        jpeg_quality=10,
        popen_factory=lambda *args, **kwargs: process,
    )

    sampler.start()
    _wait_for(lambda: store.latest() is not None and sampler.status().last_sampled_at is not None)

    latest = store.latest()
    assert latest is not None
    assert latest.jpeg_bytes == FIXTURE_JPEG
    assert latest.width == 1
    assert latest.height == 1
    assert latest.source == FrameSource.LATEST
    assert sampler.status().last_sampled_at is not None


def test_ffmpeg_sampler_reports_failed_process_exit() -> None:
    sampler = FfmpegFrameSampler(
        frame_store=_frame_store(),
        stream_url="udp://@:8554",
        ffmpeg_path="ffmpeg",
        fps=2,
        jpeg_quality=10,
        popen_factory=lambda *args, **kwargs: _FakeProcess(stdout_chunks=[], return_code=9),
    )

    sampler.start()
    _wait_for(lambda: sampler.status().state == FrameSamplerState.FAILED)

    status = sampler.status()
    assert status.state == FrameSamplerState.FAILED
    assert status.message == "ffmpeg exited with status 9."


def test_ffmpeg_sampler_stop_terminates_running_process() -> None:
    process = _FakeProcess(stdout_chunks=[], return_code=None)
    sampler = FfmpegFrameSampler(
        frame_store=_frame_store(),
        stream_url="udp://@:8554",
        ffmpeg_path="ffmpeg",
        fps=2,
        jpeg_quality=10,
        popen_factory=lambda *args, **kwargs: process,
    )

    sampler.start()
    sampler.stop()

    assert process.terminated is True


class _FakeStdout:
    def __init__(self, chunks: list[bytes], process: "_FakeProcess") -> None:
        self._chunks = chunks
        self._process = process

    def read(self, size: int) -> bytes:
        if self._chunks:
            return self._chunks.pop(0)
        if self._process.return_code is not None:
            self._process.exited = True
        sleep(0.01)
        return b""


class _FakeProcess:
    def __init__(self, *, stdout_chunks: list[bytes], return_code: int | None) -> None:
        self.return_code = return_code
        self.exited = False
        self.terminated = False
        self.stdout = _FakeStdout(stdout_chunks, self)
        self.stderr = None

    def poll(self) -> int | None:
        if self.return_code is None and not self.terminated:
            return None
        if self.return_code is not None and not self.exited:
            return None
        return self.return_code or 0

    def terminate(self) -> None:
        self.terminated = True
        self.return_code = 0
        self.exited = True

    def kill(self) -> None:
        self.terminate()

    def wait(self, timeout: float | None = None) -> int:
        self.exited = True
        return self.return_code or 0


def _frame_store() -> FrameStore:
    return FrameStore(look_ttl_seconds=60, stale_after_seconds=5)


def _wait_for(predicate, *, attempts: int = 100) -> None:
    for _ in range(attempts):
        if predicate():
            return
        sleep(0.01)
    raise AssertionError("condition was not met")

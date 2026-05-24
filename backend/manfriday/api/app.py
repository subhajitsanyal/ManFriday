import asyncio
from contextlib import suppress
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse, Response

from manfriday import __version__
from manfriday.api.contracts import (
    FrameMetadataResponse,
    FrameUnavailableResponse,
    GoProReconfigureRequest,
    GoProReconfigureResponse,
    GoProStatusResponse,
    LiveKitResponse,
    LookResponse,
    PushToTalkReleaseRequest,
    PushToTalkReleaseResponse,
    PushToTalkStartRequest,
    PushToTalkStartResponse,
    RetrievalIngestResponse,
    SessionEndRequest,
    SessionEndResponse,
    SessionStartRequest,
    SessionStartResponse,
    SessionStatusResponse,
)
from manfriday.auth.dependencies import build_auth_dependency, websocket_authorized
from manfriday.config.settings import Settings, get_settings
from manfriday.events import EventBus, EventEnvelope
from manfriday.frames import FrameStore
from manfriday.frames.models import FrameMetadata
from manfriday.gopro import GoProService, build_gopro_controller
from manfriday.livekit import LiveKitTokenIssuer
from manfriday.retrieval import ingest_local_documents
from manfriday.retrieval.summary import ingestion_summary_to_dict
from manfriday.sessions import Session, SessionStatus, SessionStore
from manfriday.voice_agent import VoiceAgentWorker
from manfriday.voice_agent.push_to_talk import PushToTalkCoordinator, PushToTalkError


def _status_snapshot(session: Session) -> EventEnvelope:
    return EventEnvelope(
        type="session.status.changed",
        session_id=session.session_id,
        payload={
            "status": session.status.value,
            "expires_at": session.expires_at.isoformat().replace("+00:00", "Z"),
            "assistant_state": "idle",
            "debug_enabled": session.debug_enabled,
        },
    )


def _status_response(session: Session) -> SessionStatusResponse:
    return SessionStatusResponse(
        session_id=session.session_id,
        status=session.status.value,
        expires_at=session.expires_at,
        assistant_state="idle",
        debug_enabled=session.debug_enabled,
    )


def _frame_response(frame: FrameMetadata) -> FrameMetadataResponse:
    return FrameMetadataResponse(
        frame_id=frame.frame_id,
        captured_at=frame.captured_at,
        age_ms=frame.age_ms(),
        width=frame.width,
        height=frame.height,
        is_pinned=frame.is_pinned,
        pin_expires_at=frame.pin_expires_at,
        used_for_analysis=frame.used_for_analysis,
        jpeg_url=f"/frame/{frame.frame_id}.jpg",
    )


def _gopro_response(status_model) -> GoProStatusResponse:
    return GoProStatusResponse(
        status=status_model.status.value,
        camera_identifier=status_model.camera_identifier,
        preview_running=status_model.preview_running,
        visual_status=status_model.visual_status.value,
        last_frame_at=status_model.last_frame_at,
        message=status_model.message,
    )


def _gopro_reconfigure_response(status_model) -> GoProReconfigureResponse:
    return GoProReconfigureResponse(
        status=status_model.status.value,
        job_id=status_model.job_id,
        started_at=status_model.started_at,
        message=status_model.message,
    )


def _not_found(session_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error": {
                "code": "session_not_found",
                "message": f"Session {session_id} was not found.",
                "retryable": False,
            },
        },
    )


def _push_to_talk_error(exc: PushToTalkError) -> HTTPException:
    return HTTPException(
        status_code=int(exc.http_status),
        detail={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "retryable": exc.retryable,
            },
        },
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    app = FastAPI(
        title="Man Friday Backend",
        version=__version__,
        docs_url="/docs" if app_settings.env != "production" else None,
        redoc_url=None,
    )
    auth_dependency = build_auth_dependency(app_settings)
    store = SessionStore(
        idle_timeout_seconds=app_settings.session_idle_timeout_seconds,
        default_debug_enabled=app_settings.debug_enabled,
    )
    event_bus = EventBus(queue_limit=app_settings.websocket_queue_limit)
    token_issuer = LiveKitTokenIssuer(app_settings)
    frame_store = FrameStore(
        look_ttl_seconds=app_settings.frame_look_ttl_seconds,
        stale_after_seconds=app_settings.frame_stale_after_seconds,
    )
    gopro_controller = build_gopro_controller(app_settings)
    gopro_service = GoProService(
        settings=app_settings,
        frame_store=frame_store,
        controller=gopro_controller,
    )
    voice_worker = VoiceAgentWorker(settings=app_settings)
    voice_orchestrator = voice_worker.build_turn_orchestrator(
        frame_store=frame_store,
        event_bus=event_bus,
    )
    push_to_talk = PushToTalkCoordinator(
        orchestrator=voice_orchestrator,
        event_bus=event_bus,
        max_duration_seconds=app_settings.push_to_talk_max_duration_seconds,
    )

    app.state.settings = app_settings
    app.state.session_store = store
    app.state.event_bus = event_bus
    app.state.livekit_token_issuer = token_issuer
    app.state.frame_store = frame_store
    app.state.gopro_controller = gopro_controller
    app.state.gopro_service = gopro_service
    app.state.voice_orchestrator = voice_orchestrator
    app.state.push_to_talk = push_to_talk

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(
                status_code=exc.status_code,
                content=exc.detail,
                headers=exc.headers,
            )
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})

    async def publish_expired_sessions() -> None:
        for expired in store.expire_idle_sessions():
            await event_bus.publish(
                EventEnvelope(
                    type="session.expired",
                    session_id=expired.session_id,
                    payload={"status": SessionStatus.EXPIRED.value},
                ),
            )

    async def publish_to_active_sessions(event_type: str, payload: dict) -> None:
        for session_id in store.active_session_ids():
            await event_bus.publish(
                EventEnvelope(
                    type=event_type,
                    session_id=session_id,
                    payload=payload,
                ),
            )

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "manfriday-backend",
            "version": __version__,
            "time": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }

    @app.post(
        "/retrieval/ingest",
        response_model=RetrievalIngestResponse,
        tags=["retrieval"],
        dependencies=[Depends(auth_dependency)],
    )
    async def retrieval_ingest() -> RetrievalIngestResponse:
        summary = ingest_local_documents(app_settings.retrieval_local_docs_dir)
        return RetrievalIngestResponse(**ingestion_summary_to_dict(summary))

    @app.post(
        "/session/start",
        response_model=SessionStartResponse,
        tags=["sessions"],
        dependencies=[Depends(auth_dependency)],
    )
    async def start_session(request: SessionStartRequest) -> SessionStartResponse:
        await publish_expired_sessions()
        session = store.start_session(
            app_instance_id=request.app_instance_id,
            debug_enabled=request.debug_enabled,
        )
        livekit = token_issuer.issue_android_token(
            session_id=session.session_id,
            room_name=session.livekit_room_name,
        )
        await event_bus.publish(_status_snapshot(session))
        return SessionStartResponse(
            session_id=session.session_id,
            livekit=LiveKitResponse(url=livekit.url, room=livekit.room, token=livekit.token),
            expires_at=session.expires_at,
            debug_enabled=session.debug_enabled,
        )

    @app.post(
        "/session/end",
        response_model=SessionEndResponse,
        tags=["sessions"],
        dependencies=[Depends(auth_dependency)],
    )
    async def end_session(request: SessionEndRequest) -> SessionEndResponse:
        await publish_expired_sessions()
        session = store.end_session(request.session_id)
        if session is None:
            raise _not_found(request.session_id)
        frame_store.clear_pin()
        await event_bus.publish(_status_snapshot(session))
        return SessionEndResponse(session_id=session.session_id, status=session.status.value)

    @app.get(
        "/session/status",
        response_model=SessionStatusResponse,
        tags=["sessions"],
        dependencies=[Depends(auth_dependency)],
    )
    async def session_status(session_id: str = Query(...)) -> SessionStatusResponse:
        await publish_expired_sessions()
        session = store.get(session_id)
        if session is None:
            raise _not_found(session_id)
        if session.status == SessionStatus.ACTIVE:
            session = store.touch(session_id)
        return _status_response(session)

    @app.post(
        "/assistant/push-to-talk/start",
        response_model=PushToTalkStartResponse,
        tags=["assistant"],
        dependencies=[Depends(auth_dependency)],
    )
    async def push_to_talk_start(
        request: PushToTalkStartRequest,
    ) -> PushToTalkStartResponse:
        await publish_expired_sessions()
        session = store.get(request.session_id)
        if session is None:
            raise _not_found(request.session_id)
        session = store.touch(session.session_id)
        try:
            started = await push_to_talk.start(session)
        except PushToTalkError as exc:
            raise _push_to_talk_error(exc) from exc
        return PushToTalkStartResponse(
            session_id=started.session_id,
            turn_id=started.turn_id,
            status=started.status,
            started_at=started.started_at,
            max_duration_seconds=started.max_duration_seconds,
        )

    @app.post(
        "/assistant/push-to-talk/release",
        response_model=PushToTalkReleaseResponse,
        tags=["assistant"],
        dependencies=[Depends(auth_dependency)],
    )
    async def push_to_talk_release(
        request: PushToTalkReleaseRequest,
    ) -> PushToTalkReleaseResponse:
        await publish_expired_sessions()
        session = store.get(request.session_id)
        if session is None:
            raise _not_found(request.session_id)
        session = store.touch(session.session_id)
        try:
            released = await push_to_talk.release(
                session=session,
                audio_ref=request.audio_ref,
                user_text=request.user_text,
                has_speech=request.has_speech,
            )
        except PushToTalkError as exc:
            raise _push_to_talk_error(exc) from exc
        result = released.result
        return PushToTalkReleaseResponse(
            session_id=released.session_id,
            turn_id=released.turn_id,
            status=released.status,
            user_text=result.user_text if result else None,
            assistant_text=result.assistant_text if result else None,
            frame_id=result.frame_id if result else None,
            visual_status=result.visual_status if result else None,
            timing_ms=result.timing_ms if result else None,
        )

    @app.get(
        "/gopro/status",
        response_model=GoProStatusResponse,
        tags=["gopro"],
        dependencies=[Depends(auth_dependency)],
    )
    async def gopro_status() -> GoProStatusResponse:
        return _gopro_response(gopro_service.get_status())

    @app.post(
        "/gopro/start-preview",
        response_model=GoProStatusResponse,
        tags=["gopro"],
        dependencies=[Depends(auth_dependency)],
    )
    async def start_preview() -> GoProStatusResponse:
        status_model = gopro_service.start_preview()
        latest = frame_store.latest()
        if latest is not None:
            await publish_to_active_sessions(
                "frame.latest.updated",
                _frame_response(latest).model_dump(mode="json"),
            )
        return _gopro_response(status_model)

    @app.post(
        "/gopro/stop-preview",
        response_model=GoProStatusResponse,
        tags=["gopro"],
        dependencies=[Depends(auth_dependency)],
    )
    async def stop_preview() -> GoProStatusResponse:
        return _gopro_response(gopro_service.stop_preview())

    @app.post(
        "/gopro/reconfigure",
        response_model=GoProReconfigureResponse,
        tags=["gopro"],
        dependencies=[Depends(auth_dependency)],
    )
    async def reconfigure_gopro(
        request: GoProReconfigureRequest,
    ) -> GoProReconfigureResponse:
        if not request.confirm_clear_credentials:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": {
                        "code": "confirmation_required",
                        "message": "confirm_clear_credentials must be true to reconfigure GoPro.",
                        "retryable": False,
                    },
                },
            )
        reconfigure_status = gopro_service.reconfigure()
        await publish_to_active_sessions(
            "gopro.reconfigure.started",
            _gopro_reconfigure_response(reconfigure_status).model_dump(mode="json"),
        )
        return _gopro_reconfigure_response(reconfigure_status)

    @app.post(
        "/gopro/reconfigure/cancel",
        response_model=GoProReconfigureResponse,
        tags=["gopro"],
        dependencies=[Depends(auth_dependency)],
    )
    async def cancel_gopro_reconfigure() -> GoProReconfigureResponse:
        reconfigure_status = gopro_service.cancel_reconfigure()
        if reconfigure_status.status.value == "cancelled":
            await publish_to_active_sessions(
                "gopro.reconfigure.cancelled",
                _gopro_reconfigure_response(reconfigure_status).model_dump(mode="json"),
            )
        return _gopro_reconfigure_response(reconfigure_status)

    @app.get(
        "/frame/latest",
        response_model=FrameMetadataResponse | FrameUnavailableResponse,
        tags=["frames"],
        dependencies=[Depends(auth_dependency)],
    )
    async def latest_frame() -> FrameMetadataResponse | FrameUnavailableResponse:
        latest = frame_store.latest_if_healthy()
        if latest is None:
            visual_status = "degraded" if gopro_service.preview_running() else "unavailable"
            return FrameUnavailableResponse(
                visual_status=visual_status,
                message="No fresh frame is available.",
            )
        return _frame_response(latest)

    @app.post(
        "/frame/look",
        response_model=LookResponse,
        tags=["frames"],
        dependencies=[Depends(auth_dependency)],
    )
    async def look() -> LookResponse:
        frame = frame_store.pin_latest()
        if frame is None or frame.pin_expires_at is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": {
                        "code": "frame_unavailable",
                        "message": "No fresh frame is available to pin.",
                        "retryable": True,
                    },
                },
            )
        await publish_to_active_sessions(
            "frame.pinned",
            _frame_response(frame).model_dump(mode="json"),
        )
        return LookResponse(
            frame_id=frame.frame_id,
            captured_at=frame.captured_at,
            pin_expires_at=frame.pin_expires_at,
            jpeg_url=f"/frame/{frame.frame_id}.jpg",
        )

    @app.get(
        "/frame/{frame_id}.jpg",
        tags=["frames"],
        dependencies=[Depends(auth_dependency)],
    )
    async def frame_jpeg(frame_id: str) -> Response:
        frame = frame_store.get(frame_id)
        if frame is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "frame_not_found",
                        "message": f"Frame {frame_id} was not found.",
                        "retryable": False,
                    },
                },
            )
        return Response(
            content=frame.jpeg_bytes,
            media_type="image/jpeg",
            headers={"Cache-Control": "no-store"},
        )

    @app.websocket("/ws")
    async def websocket_events(websocket: WebSocket, session_id: str = Query(...)) -> None:
        if not websocket_authorized(websocket, app_settings):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        await publish_expired_sessions()
        session = store.get(session_id)
        if session is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        await websocket.accept()
        queue = event_bus.subscribe(session_id)
        try:
            await websocket.send_json(_status_snapshot(session).model_dump(mode="json"))
            while True:
                event_task = asyncio.create_task(queue.get())
                receive_task = asyncio.create_task(websocket.receive_text())
                done, pending = await asyncio.wait(
                    {event_task, receive_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
                if receive_task in done:
                    store.touch(session_id)
                    message = receive_task.result()
                    if message == "ping":
                        current = store.get(session_id)
                        if current is not None:
                            await websocket.send_json(
                                _status_snapshot(current).model_dump(mode="json"),
                            )
                if event_task in done:
                    event = event_task.result()
                    await websocket.send_json(event.model_dump(mode="json"))
        except WebSocketDisconnect:
            return
        finally:
            event_bus.unsubscribe(session_id, queue)

    return app

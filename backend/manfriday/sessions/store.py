from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from manfriday.sessions.models import Session, SessionStatus


class SessionStore:
    def __init__(
        self,
        *,
        idle_timeout_seconds: int,
        default_debug_enabled: bool,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._idle_timeout = timedelta(seconds=idle_timeout_seconds)
        self._default_debug_enabled = default_debug_enabled
        self._now_fn = now_fn or (lambda: datetime.now(UTC))
        self._sessions: dict[str, Session] = {}
        self._app_sessions: dict[str, str] = {}

    def start_session(
        self,
        *,
        app_instance_id: str | None,
        debug_enabled: bool | None,
    ) -> Session:
        self.expire_idle_sessions()
        if app_instance_id:
            existing_id = self._app_sessions.get(app_instance_id)
            if existing_id:
                existing = self._sessions.get(existing_id)
                if existing and existing.status == SessionStatus.ACTIVE:
                    return self.touch(existing.session_id)

        now = self._now()
        session_id = self._new_session_id()
        session = Session(
            session_id=session_id,
            app_instance_id=app_instance_id,
            livekit_room_name=f"manfriday_{session_id}",
            created_at=now,
            last_activity_at=now,
            expires_at=now + self._idle_timeout,
            debug_enabled=self._default_debug_enabled if debug_enabled is None else debug_enabled,
        )
        self._sessions[session_id] = session
        if app_instance_id:
            self._app_sessions[app_instance_id] = session_id
        return session

    def get(self, session_id: str) -> Session | None:
        self.expire_idle_sessions()
        return self._sessions.get(session_id)

    def active_session_ids(self) -> list[str]:
        self.expire_idle_sessions()
        return [
            session.session_id
            for session in self._sessions.values()
            if session.status == SessionStatus.ACTIVE
        ]

    def end_session(self, session_id: str) -> Session | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        session.status = SessionStatus.ENDED
        session.memory.clear()
        session.active_livekit_participants.clear()
        if session.app_instance_id:
            self._app_sessions.pop(session.app_instance_id, None)
        return session

    def touch(self, session_id: str) -> Session:
        session = self._sessions[session_id]
        if session.status == SessionStatus.ACTIVE:
            now = self._now()
            session.last_activity_at = now
            session.expires_at = now + self._idle_timeout
        return session

    def expire_idle_sessions(self) -> list[Session]:
        now = self._now()
        expired: list[Session] = []
        for session in self._sessions.values():
            if session.status == SessionStatus.ACTIVE and session.expires_at <= now:
                session.status = SessionStatus.EXPIRED
                session.memory.clear()
                session.active_livekit_participants.clear()
                if session.app_instance_id:
                    self._app_sessions.pop(session.app_instance_id, None)
                expired.append(session)
        return expired

    def _now(self) -> datetime:
        now = self._now_fn()
        if now.tzinfo is None:
            return now.replace(tzinfo=UTC)
        return now

    @staticmethod
    def _new_session_id() -> str:
        from uuid import uuid4

        return f"sess_{uuid4().hex}"

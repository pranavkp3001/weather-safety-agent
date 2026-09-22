import time
import threading
from typing import Optional, Any
from pydantic import BaseModel, Field
from backend.app.services.geocoding import LocationInfo


class ConversationTurn(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    timestamp: float = Field(default_factory=time.time)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionContext(BaseModel):
    session_id: str
    location: Optional[LocationInfo] = None
    activity: Optional[str] = None
    category: Optional[str] = None
    time_reference: Optional[str] = None
    turns: list[ConversationTurn] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    def add_turn(self, role: str, content: str, metadata: Optional[dict[str, Any]] = None):
        self.turns.append(ConversationTurn(role=role, content=content, metadata=metadata or {}))
        self.updated_at = time.time()


class SessionManager:
    """
    Thread-safe in-memory store for conversational session context.
    Strict Invalidation Principle:
    Weather facts are NEVER stored or reused across turns.
    Only location, activity, category, and dialog turns persist.
    """
    def __init__(self, ttl_seconds: int = 3600):
        self.ttl_seconds = ttl_seconds
        self._sessions: dict[str, SessionContext] = {}
        self._lock = threading.Lock()

    def get_or_create(self, session_id: str) -> SessionContext:
        with self._lock:
            self._cleanup_expired()
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionContext(session_id=session_id)
            return self._sessions[session_id]

    def get(self, session_id: str) -> Optional[SessionContext]:
        with self._lock:
            self._cleanup_expired()
            return self._sessions.get(session_id)

    def update_context(
        self,
        session_id: str,
        location: Optional[LocationInfo] = None,
        activity: Optional[str] = None,
        category: Optional[str] = None,
        time_reference: Optional[str] = None,
    ) -> SessionContext:
        with self._lock:
            ctx = self.get_or_create(session_id)
            if location is not None:
                ctx.location = location
            if activity is not None:
                ctx.activity = activity
            if category is not None:
                ctx.category = category
            if time_reference is not None:
                ctx.time_reference = time_reference
            ctx.updated_at = time.time()
            return ctx

    def clear(self, session_id: str) -> None:
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]

    def _cleanup_expired(self) -> None:
        now = time.time()
        expired = [sid for sid, ctx in self._sessions.items() if now - ctx.updated_at > self.ttl_seconds]
        for sid in expired:
            del self._sessions[sid]


# Singleton in-memory session manager
session_manager = SessionManager()

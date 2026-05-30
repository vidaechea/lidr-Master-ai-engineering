"""In-memory session store for conversational estimation workflows.

Volatility trade-off accepted deliberately:
  Sessions live only as long as the process. This is intentional in this phase
  because the product priority is to validate the conversational UX quickly.
  Introducing Redis or a DB would require auth, TTL policies, serialization, and
  ops overhead that add no learning value at this stage. When the service is
  restarted or scaled horizontally, sessions are lost — callers must start a new
  one. This is communicated in the API contract and is acceptable during MVP.
"""

from __future__ import annotations

import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from app.config import settings

if TYPE_CHECKING:
    from app.services.summarizer_service import SummarizerService

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Maximum number of user turns kept in the sliding window per session.
#: In the common case, one turn is a user message plus its assistant reply.
#: Once exceeded, the oldest turn is evicted while preserving the system prompt.
#: Overridable via ``settings.max_conversation_turns``.
MAX_TURNS: int = 6

# Backward-compatible export used by older tests/callers.
MAX_CONVERSATION_TURNS: int = MAX_TURNS

# ---------------------------------------------------------------------------
# Message type
# ---------------------------------------------------------------------------

MessageRole = Literal["system", "user", "assistant"]


@dataclass
class Message:
    """A single LLM message with a role and text content."""

    role: MessageRole
    content: str


# ---------------------------------------------------------------------------
# ConversationHistory
# ---------------------------------------------------------------------------


class ConversationHistory:
    """Bounded message list with a sliding-window eviction strategy.

    The system prompt (role="system") is pinned at position 0 and is **never**
    evicted. Non-system messages are stored in chronological order.
    The window size is enforced by counting user turns; when the number of
    user messages exceeds ``max_turns``, the oldest user turn is removed.
    If that user message is followed by its assistant response, the response is
    also removed to keep turn boundaries coherent.

    Args:
        system_prompt: Optional system message injected once at construction.
        max_turns: Maximum number of *user+assistant pairs* to retain.
            Defaults to :data:`MAX_TURNS` (6).  Configurable via
            ``settings.max_conversation_turns``.
    """

    def __init__(
        self,
        system_prompt: str | None = None,
        max_turns: int = MAX_TURNS,
    ) -> None:
        self._system_prompt: Message | None = (
            Message(role="system", content=system_prompt) if system_prompt else None
        )
        # Unbounded deque — eviction is handled manually in add() so we always
        # remove complete pairs rather than splitting them.
        self._turns: deque[Message] = deque()
        self._max_turns: int = max_turns

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, role: MessageRole, content: str) -> None:
        """Append a message; system messages replace the pinned prompt.

        After adding a non-system message, the sliding window is enforced by
        number of user turns. If user turns exceed ``max_turns``, the oldest
        user turn is evicted (and its assistant response, when present).
        """
        if role == "system":
            self._system_prompt = Message(role="system", content=content)
            return

        self._turns.append(Message(role=role, content=content))

        # Evict oldest user turn when the window is exceeded.
        while self.turn_count > self._max_turns:
            while self._turns:
                oldest = self._turns.popleft()
                if oldest.role == "user":
                    if self._turns and self._turns[0].role == "assistant":
                        self._turns.popleft()
                    break

    def messages(self) -> list[Message]:
        """Return all messages in chronological order, system prompt first."""
        result: list[Message] = []
        if self._system_prompt:
            result.append(self._system_prompt)
        result.extend(self._turns)
        return result

    def as_dicts(self) -> list[dict[str, str]]:
        """Serialise to the ``{"role": ..., "content": ...}`` format expected by LLM APIs."""
        return [{"role": m.role, "content": m.content} for m in self.messages()]

    def to_messages_list(self, system_prompt: str | None = None) -> list[dict[str, str]]:
        """Return the messages array ready to pass directly to the LLM API.

        The system prompt is refreshed on every call so it always reflects the
        latest ``project_metadata`` injected by the caller.  Pass a freshly
        rendered system prompt string each turn; if *system_prompt* is ``None``
        the previously stored system prompt is used unchanged.

        Args:
            system_prompt: A freshly rendered system prompt string (e.g. built
                by :class:`~app.services.helpers.prompt_builder.PromptBuilder`
                with the current :class:`~app.services.sessions.ProjectMetadata`).
                When provided it **replaces** the stored system prompt for this
                call and for all subsequent calls that do not supply one.

        Returns:
            ``[{"role": "system", ...}, {"role": "user", ...}, ...]`` ready for
            the LLM provider client.
        """
        if system_prompt is not None:
            self._system_prompt = Message(role="system", content=system_prompt)
        messages: list[dict[str, str]] = []
        if self._system_prompt:
            messages.append({"role": self._system_prompt.role, "content": self._system_prompt.content})
        messages.extend({"role": m.role, "content": m.content} for m in self._turns)
        return messages

    @property
    def turn_count(self) -> int:
        """Number of user turns currently stored."""
        return sum(1 for message in self._turns if message.role == "user")

    def __len__(self) -> int:
        return len(self._turns) + (1 if self._system_prompt else 0)


# ---------------------------------------------------------------------------
# ProjectMetadata
# ---------------------------------------------------------------------------


class ProjectMetadata(BaseModel):
    """Structured metadata extracted progressively across conversation turns.

    Fields are intentionally optional so they can be populated incrementally
    as the model extracts information from successive user messages.
    """

    project_name: str | None = Field(
        default=None,
        description="Human-readable name for the project under estimation.",
    )
    assumed_team_size: int | None = Field(
        default=None,
        ge=1,
        description="Number of team members assumed for the estimation.",
    )
    mentioned_technologies: list[str] = Field(
        default_factory=list,
        description="Technologies, frameworks or platforms mentioned so far.",
    )
    agreed_scope: str | None = Field(
        default=None,
        description="Free-text summary of the agreed project scope.",
    )


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


@dataclass
class Session:
    """Container for all stateful data associated with a single conversation.

    Args:
        session_id: UUID v4 string that uniquely identifies this session.
        history: Sliding-window message log.
        metadata: Incrementally-populated project metadata.
    """

    session_id: str
    history: ConversationHistory = field(default_factory=ConversationHistory)
    metadata: ProjectMetadata = field(default_factory=ProjectMetadata)
    last_resolved_tier: str | None = field(default=None)
    last_tier_rule: str | None = field(default=None)
    _summarizer: SummarizerService | None = field(default=None, init=False, repr=False)

    def get_summarizer(self) -> SummarizerService:
        """Lazy-load the SummarizerService on first access (avoids circular import)."""
        if self._summarizer is None:
            from app.services.summarizer_service import SummarizerService

            self._summarizer = SummarizerService()
        return self._summarizer


# ---------------------------------------------------------------------------
# SessionStore — process-level singleton
# ---------------------------------------------------------------------------


class SessionStore:
    """In-memory registry that maps session_id → Session.

    A module-level singleton (``store``) is exposed so all routers and
    services share the same dict within the process lifetime.  No locking is
    needed because FastAPI's default event loop is single-threaded; async
    handlers are interleaved but not truly concurrent at the Python level.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def create(self) -> Session:
        """Allocate a new Session with a fresh UUID v4 identifier."""
        session_id = str(uuid.uuid4())
        session = Session(
            session_id=session_id,
            history=ConversationHistory(max_turns=settings.max_conversation_turns),
        )
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        """Return the Session for *session_id*, or ``None`` if not found."""
        return self._sessions.get(session_id)

    def get_all(self) -> list[Session]:
        """Return all sessions as a list."""
        return list(self._sessions.values())

    def __len__(self) -> int:
        return len(self._sessions)


#: Module-level singleton — import this in routers and services.
store: SessionStore = SessionStore()

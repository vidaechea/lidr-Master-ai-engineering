from pydantic import BaseModel, Field

from app.services.sessions import ProjectMetadata


class SessionCreateResponse(BaseModel):
    """Response body returned when a new session is created."""

    session_id: str = Field(
        description="UUID v4 that identifies the session. Pass this in every subsequent request."
    )


class SessionMessageResponse(BaseModel):
    """Single message in the persisted conversation history."""

    role: str
    content: str


class SessionStateResponse(BaseModel):
    """Current persisted state for a conversation session."""

    session_id: str
    project_metadata: ProjectMetadata
    history: list[SessionMessageResponse]
    turn_count: int = Field(
        description="Number of user turns currently stored in the session history window."
    )


class SessionListItem(BaseModel):
    """Summary item for a session in the list view."""

    session_id: str = Field(description="UUID v4 that identifies the session.")
    project_name: str | None = Field(
        default=None, description="Project name extracted from conversation, if available."
    )
    turn_count: int = Field(
        default=0, description="Number of user turns in this session."
    )
    last_message_content: str | None = Field(
        default=None,
        description="First 200 characters of the last assistant message for preview.",
    )

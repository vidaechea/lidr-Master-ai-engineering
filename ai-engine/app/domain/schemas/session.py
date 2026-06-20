from pydantic import BaseModel, Field

from app.generation.conversation.sessions import ProjectMetadata


class SessionCreateResponse(BaseModel):
    """Response body returned when a new session is created."""

    session_id: str = Field(
        description="UUID v4 that identifies the session. Pass this in every subsequent request."
    )


class SessionMessageResponse(BaseModel):
    """Single message in the persisted conversation history."""

    role: str
    content: str


class AnchorResponse(BaseModel):
    """A heuristic anchor marking a turn with critical information."""

    turn_number: int = Field(description="Which user turn contained this critical information.")
    anchor_type: str = Field(
        description="Category: metadata_extraction, scope_change, decision_point, risk_identified, etc."
    )
    key_information: str = Field(description="The extracted or flagged content.")
    summary: str = Field(description="Brief explanation of why this turn is critical.")


class SessionStateResponse(BaseModel):
    """Current persisted state for a conversation session."""

    session_id: str
    project_metadata: ProjectMetadata
    history: list[SessionMessageResponse]
    turn_count: int = Field(
        description="Number of user turns currently stored in the session history window."
    )
    message_count: int = Field(
        description="Total number of messages (user + assistant + system) in the session history."
    )
    anchors_count: int = Field(
        default=0,
        description="Total number of critical information anchors generated so far.",
    )
    summary_chars: int = Field(
        default=0,
        description="Character count of the accumulative summary of critical information.",
    )
    last_resolved_tier: str | None = Field(
        default=None,
        description="The last user tier that was resolved during this session.",
    )
    last_tier_rule: str | None = Field(
        default=None,
        description="The last tier rule or constraint that was applied to this session.",
    )
    anchors: list[AnchorResponse] = Field(
        default_factory=list,
        description="List of all anchors detected in this session.",
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


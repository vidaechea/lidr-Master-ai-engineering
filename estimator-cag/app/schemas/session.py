from pydantic import BaseModel, Field


class SessionCreateResponse(BaseModel):
    """Response body returned when a new session is created."""

    session_id: str = Field(
        description="UUID v4 that identifies the session. Pass this in every subsequent request."
    )

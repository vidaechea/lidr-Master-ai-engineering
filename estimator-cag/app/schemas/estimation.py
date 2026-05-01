from enum import Enum
from typing import Optional
from pydantic import BaseModel

class ExampleFormat(str, Enum):
    MARKDOWN = "markdown"
    JSON = "json"
    NARRATIVE = "narrative"

class EstimationRequest(BaseModel):
    transcription: str


class EstimationResponse(BaseModel):
    estimation: str
    model: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: Optional[int]
    turn_cost_usd: float
    total_cost_usd: float
    response_id: str
    estimated_input_tokens: int
    estimated_precall_cost_usd: float
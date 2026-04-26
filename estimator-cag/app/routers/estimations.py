from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.context.examples import ESTIMATION_EXAMPLES
from app.services.llm_service import estimate

router = APIRouter(prefix="/estimations", tags=["estimations"])


class EstimationRequest(BaseModel):
    description: str


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


class ExampleItem(BaseModel):
    meeting_summary: str
    estimation: str


@router.get("/examples", response_model=list[ExampleItem])
def get_examples():
    return [
        ExampleItem(meeting_summary=ex.meeting_summary, estimation=ex.estimation)
        for ex in ESTIMATION_EXAMPLES
    ]


@router.post("/", response_model=EstimationResponse)
async def create_estimation(request: EstimationRequest):
    result = await estimate(request.description)
    if result.get("error"):
        status_code = result.get("status_code", 500)
        raise HTTPException(status_code=status_code, detail=result["message"])
    return EstimationResponse(
        estimation=result["content"],
        model=result["model"],
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        reasoning_tokens=result["reasoning_tokens"],
        turn_cost_usd=result["turn_cost_usd"],
        total_cost_usd=result["total_cost_usd"],
        response_id=result["response_id"],
        estimated_input_tokens=result["estimated_input_tokens"],
        estimated_precall_cost_usd=result["estimated_precall_cost_usd"],
    )

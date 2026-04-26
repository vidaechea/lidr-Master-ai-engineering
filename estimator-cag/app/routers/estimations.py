from fastapi import APIRouter
from pydantic import BaseModel
from app.context.examples import ESTIMATION_EXAMPLES
from app.services.llm_service import estimate

router = APIRouter(prefix="/estimations", tags=["estimations"])


class EstimationRequest(BaseModel):
    description: str


class EstimationResponse(BaseModel):
    estimation: str


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
    return EstimationResponse(estimation=result)

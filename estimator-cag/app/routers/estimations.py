from fastapi import APIRouter
from pydantic import BaseModel
from app.services.llm_service import estimate

router = APIRouter(prefix="/estimations", tags=["estimations"])


class EstimationRequest(BaseModel):
    description: str


class EstimationResponse(BaseModel):
    estimation: str


@router.post("/", response_model=EstimationResponse)
async def create_estimation(request: EstimationRequest):
    result = await estimate(request.description)
    return EstimationResponse(estimation=result)

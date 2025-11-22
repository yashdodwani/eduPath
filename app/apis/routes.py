from fastapi import APIRouter, HTTPException, status
from app.models.schemas import UserProfile, RoadmapResponse
from app.services.agent_service import AgentWorkflow

router = APIRouter()

@router.post("/generate-roadmap", response_model=RoadmapResponse, status_code=status.HTTP_200_OK)
async def generate_roadmap(profile: UserProfile):
    """
    Triggers the Multi-Agent System to generate a personalized learning path.
    """
    try:
        workflow = AgentWorkflow()
        result = await workflow.generate_learning_path(profile)
        return result
    except Exception as e:
        # In production, log the full error to backend logs
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent Swarm Failure: {str(e)}"
        )

@router.get("/health")
def health_check():
    return {"status": "active", "service": "Agentic Learning Backend"}
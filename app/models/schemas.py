from typing import List, Optional, Dict, Literal
from pydantic import BaseModel, Field

# --- Input Models (Request Body) ---

class UserProfile(BaseModel):
    name: str = Field(..., example="Alex")
    current_role: str = Field(..., example="Student")
    target_role: str = Field(..., example="React Developer")
    current_skills: List[str] = Field(..., example=["HTML", "CSS", "JavaScript Basics"])
    preferred_style: Literal["Video", "Text", "Interactive"] = Field(default="Video", description="Feature D: VARK Model")
    experience_level: str = Field(default="Beginner", example="Beginner")

# --- Output Models (Response Body) ---

class LearningResource(BaseModel):
    title: str
    url: str
    type: Literal["Video", "Article", "Course", "Documentation"]
    duration: str
    reason: str  # Why this specific link was chosen (Curator Agent)

class RoadmapModule(BaseModel):
    id: int
    module_name: str
    description: str
    skills_covered: List[str]
    resources: List[LearningResource]
    why_needed: str = Field(..., description="Feature C: Explainable AI - Agent reasoning")
    estimated_time: str

class MarketTrend(BaseModel):
    skill: str
    demand_level: str  # High, Critical, Emerging
    growth_metric: str # e.g., "+15% YoY"

class AgentLog(BaseModel):
    agent_name: str
    action: str
    timestamp: str

class RoadmapResponse(BaseModel):
    market_analysis: List[MarketTrend]
    roadmap: List[RoadmapModule]
    agent_logs: List[AgentLog]
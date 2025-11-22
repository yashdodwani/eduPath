from typing import List, Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    roadmaps: List["Roadmap"] = Relationship(back_populates="user")

class Roadmap(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    target_role: str
    market_analysis: str  # store JSON as text
    profile: Optional[str] = None  # store original UserProfile JSON
    created_at: datetime = Field(default_factory=datetime.utcnow)

    modules: List["Module"] = Relationship(back_populates="roadmap")
    logs: List["AgentLog"] = Relationship(back_populates="roadmap")
    progress: List["ModuleProgress"] = Relationship(back_populates="roadmap")

    # Add the reverse relationship to User so back_populates matches
    user: Optional[User] = Relationship(back_populates="roadmaps")

class Module(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    roadmap_id: int = Field(foreign_key="roadmap.id")
    module_index: int
    module_name: str
    description: str
    skills_covered: str  # JSON list as text
    why_needed: str
    estimated_time: str

    resources: List["Resource"] = Relationship(back_populates="module")
    roadmap: Optional[Roadmap] = Relationship(back_populates="modules")

class Resource(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    module_id: int = Field(foreign_key="module.id")
    title: str
    url: str
    type: str
    duration: str
    reason: str

    module: Optional[Module] = Relationship(back_populates="resources")

class AgentLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    roadmap_id: int = Field(foreign_key="roadmap.id")
    agent_name: str
    action: str
    timestamp: str

    roadmap: Optional[Roadmap] = Relationship(back_populates="logs")

class ModuleProgress(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    roadmap_id: int = Field(foreign_key="roadmap.id")
    module_id: int = Field(foreign_key="module.id")
    status: str = Field(default="incomplete")  # 'incomplete'|'completed'
    completed_at: Optional[datetime] = None

    roadmap: Optional[Roadmap] = Relationship(back_populates="progress")

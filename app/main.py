import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.apis.routes import router as api_router
from app.db.session import init_db

# Initialize App
app = FastAPI(
    title="Agentic Learning Path Generator",
    description="Backend for AI-driven personalized education using Gemini 2.5 Flash.",
    version="1.0.0"
)

# CORS Configuration (Allow React Frontend)
origins = [
    "http://localhost:3000",
    "http://localhost:5173",

    # Lovable preview URL
    "https://id-preview--3a7b2998-fc47-4b75-9b46-fbfbfd416a18.lovable.app",

    # If you have final deployed frontend, add here:
    "https://your-frontend.lovable.app"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(api_router, prefix="/api/v1", tags=["Roadmap Generation"])

# Root endpoint
@app.get("/")
def root():
    return {"message": "Agentic Learning System API is Online 🚀"}


@app.on_event("startup")
def on_startup():
    # Initialize the DB (create tables if they don't exist)
    init_db()


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
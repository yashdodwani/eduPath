import os
from dotenv import load_dotenv
from app.services.youtube_service import YouTubeSearchService

load_dotenv()

# Initialize service
youtube = YouTubeSearchService()

# Test search
videos = youtube.search_for_module(
    module_name="FastAPI Fundamentals",
    skills=["FastAPI", "Pydantic", "REST API"],
    target_role="Python Backend Developer",
    count=3
)

# Print results
for i, video in enumerate(videos, 1):
    print(f"\n{i}. {video['title']}")
    print(f"   URL: {video['url']}")
    print(f"   Duration: {video['duration']}")
    print(f"   Views: {video.get('views', 'N/A')}")
    print(f"   Channel: {video['channel']}")
    print(f"   Reason: {video['reason']}")
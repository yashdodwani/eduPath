import os
import json
import datetime
from dotenv import load_dotenv
import google.generativeai as genai
from app.models.schemas import UserProfile, RoadmapResponse, AgentLog
from app.utils.prompts import MARKET_ANALYST_PROMPT, ARCHITECT_PROMPT, CURATOR_PROMPT, CRITIC_PROMPT

# Load environment variables from .env (if present)
# This allows local development to place GEMINI_API_KEY in a .env file.
load_dotenv()

# Load Gemini API key from environment and configure the client
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    # Fail fast so callers know configuration is missing; in production you may want to
    # log and continue or use a safer fallback.
    raise RuntimeError("GEMINI_API_KEY is not set in the environment. Set it in your .env or environment variables.")

genai.configure(api_key=API_KEY)

# Instantiate the model after configuration
model = genai.GenerativeModel("gemini-2.5-flash")


class AgentWorkflow:
    def __init__(self):
        self.logs = []

    def _log(self, agent: str, action: str):
        """Helper to capture internal thought process"""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.logs.append(AgentLog(agent_name=agent, action=action, timestamp=timestamp))

    async def generate_learning_path(self, profile: UserProfile) -> RoadmapResponse:

        # --- STEP 1: MARKET ANALYST AGENT ---
        self._log("Market Analyst", f"Scanning job boards for '{profile.target_role}'...")
        market_response = model.generate_content(
            MARKET_ANALYST_PROMPT.format(target_role=profile.target_role)
        )
        # Clean generic markdown json blocks ```json ... ```
        market_data = self._clean_json(market_response.text)
        self._log("Market Analyst", f"Identified {len(market_data)} critical skills.")

        # --- STEP 2: ARCHITECT AGENT ---
        self._log("Architect", "Designing curriculum structure based on gap analysis...")
        architect_response = model.generate_content(
            ARCHITECT_PROMPT.format(
                current_skills=profile.current_skills,
                target_role=profile.target_role,
                market_trends=json.dumps(market_data)
            )
        )
        structure_data = self._clean_json(architect_response.text)
        self._log("Architect", f"Created {len(structure_data)} modules.")

        # --- STEP 3: CURATOR AGENT ---
        self._log("Curator", f"Sourcing {profile.preferred_style} resources for modules...")
        curator_response = model.generate_content(
            CURATOR_PROMPT.format(
                preferred_style=profile.preferred_style,
                modules=json.dumps(structure_data)
            )
        )
        curated_data = self._clean_json(curator_response.text)

        # --- STEP 4: CRITIC AGENT ---
        self._log("Critic", "Validating logical flow and prerequisites...")
        # In a real complex app, the critic might loop back to Architect.
        # Here we do a single pass validation.
        critic_response = model.generate_content(
            CRITIC_PROMPT.format(curated_path=json.dumps(curated_data))
        )
        final_roadmap = self._clean_json(critic_response.text)
        self._log("System", "Roadmap generation complete.")

        return RoadmapResponse(
            market_analysis=market_data,
            roadmap=final_roadmap,
            agent_logs=self.logs
        )

    def _clean_json(self, text_response: str):
        """
        Gemini often returns ```json ... ```. This helper strips it.
        """
        clean_text = text_response.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(clean_text)
        except json.JSONDecodeError:
            # Fallback: In production, retry logic or regex extraction goes here
            print(f"Failed to parse JSON: {clean_text}")
            return []
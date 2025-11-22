import os
import json
import datetime
import re
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
        # Clean generic markdown json blocks or extract JSON from free text
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

        # Normalize the final roadmap to match Pydantic schemas
        normalized_roadmap = self._normalize_roadmap(final_roadmap)

        return RoadmapResponse(
            market_analysis=market_data,
            roadmap=normalized_roadmap,
            agent_logs=self.logs
        )

    def _normalize_resource_type(self, raw_type: str) -> str:
        """Map free-form resource type strings into the allowed literals.
        Allowed: 'Video', 'Article', 'Course', 'Documentation'
        """
        if not raw_type:
            return "Article"
        t = raw_type.lower()
        if "video" in t:
            return "Video"
        if "course" in t:
            return "Course"
        if "doc" in t or "documentation" in t or "docs" in t:
            return "Documentation"
        if "article" in t or "blog" in t or "post" in t:
            return "Article"
        # default fallback
        return "Article"

    def _ensure_url(self, url: str) -> str:
        if not url or not isinstance(url, str) or not url.strip():
            return "https://example.com"
        return url.strip()

    def _normalize_roadmap(self, raw) -> list:
        """Convert the model output into a list of modules matching RoadmapModule.
        Handles several common shapes: a list of modules directly, or a dict with
        a top-level key like 'learning_path' or 'roadmap'.
        """
        modules = []
        if not raw:
            return []

        # If the model wrapped the list in a dict like { "learning_path": [...] }
        if isinstance(raw, dict):
            if "learning_path" in raw and isinstance(raw["learning_path"], list):
                modules = raw["learning_path"]
            elif "roadmap" in raw and isinstance(raw["roadmap"], list):
                modules = raw["roadmap"]
            else:
                # If the dict itself looks like a single module, convert to list
                # Heuristic: has 'module_name' key
                if "module_name" in raw:
                    modules = [raw]
                else:
                    # try to find the first list value inside
                    for v in raw.values():
                        if isinstance(v, list):
                            modules = v
                            break
        elif isinstance(raw, list):
            modules = raw

        normalized = []
        for idx, m in enumerate(modules):
            if not isinstance(m, dict):
                # skip unexpected entries
                continue
            module_name = m.get("module_name") or m.get("title") or m.get("name") or f"Module {idx+1}"
            description = m.get("description") or m.get("desc") or ""
            skills = m.get("skills_covered") or m.get("skills") or []
            why_needed = m.get("why_needed") or m.get("why") or ""
            estimated_time = m.get("estimated_time") or m.get("duration") or ""

            raw_resources = m.get("resources") or []
            resources = []
            for r in raw_resources:
                if not isinstance(r, dict):
                    continue
                title = r.get("title") or r.get("name") or "Untitled Resource"
                url = self._ensure_url(r.get("url") or r.get("link") or "")
                raw_type = r.get("type") or r.get("format") or ""
                rtype = self._normalize_resource_type(raw_type)
                duration = r.get("duration") or r.get("length") or ""
                reason = r.get("reason") or r.get("why") or ""
                resources.append({
                    "title": title,
                    "url": url,
                    "type": rtype,
                    "duration": duration,
                    "reason": reason
                })

            normalized.append({
                "id": idx + 1,
                "module_name": module_name,
                "description": description,
                "skills_covered": skills if isinstance(skills, list) else [skills],
                "resources": resources,
                "why_needed": why_needed,
                "estimated_time": estimated_time
            })

        return normalized

    def _extract_json_substring(self, text: str):
        """Find the first balanced JSON object or array in `text` and return it as a substring.
        This scans for the first '{' or '[' and then walks forward tracking string and escape
        states so we can correctly match nested braces/brackets.
        Returns None if no balanced JSON substring is found.
        """
        for start_idx, ch in enumerate(text):
            if ch not in '{[':
                continue
            stack = [ch]
            in_string = False
            escape = False
            for i in range(start_idx + 1, len(text)):
                c = text[i]
                if escape:
                    escape = False
                    continue
                if c == '\\':
                    escape = True
                    continue
                if c == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if c in '{[':
                    stack.append(c)
                elif c in '}]':
                    if not stack:
                        break
                    last = stack[-1]
                    if (last == '{' and c == '}') or (last == '[' and c == ']'):
                        stack.pop()
                        if not stack:
                            return text[start_idx:i+1]
                    else:
                        # mismatched closing bracket
                        break
        return None

    def _clean_json(self, text_response: str):
        """
        Extracts and parses the first JSON object/array found in the model text.
        Handles common code-fence formatting (```json ... ```) and also free-text
        responses that append a JSON blob at the end.
        Returns a Python object (list/dict) on success or an empty list on failure.
        """
        # 1) Try to find fenced JSON blocks first
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text_response, re.DOTALL | re.IGNORECASE)
        candidate = None
        if fenced:
            candidate = fenced.group(1).strip()
        else:
            # 2) Otherwise, attempt to extract a balanced JSON substring from anywhere in the text
            candidate = self._extract_json_substring(text_response)

        if not candidate:
            # No JSON found
            print("Failed to parse JSON: no JSON-like substring found in response")
            return []

        # Try to parse the candidate JSON
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            # As a final fallback, try to locate a JSON substring inside the candidate
            inner = self._extract_json_substring(candidate)
            if inner:
                try:
                    return json.loads(inner)
                except json.JSONDecodeError:
                    pass
            # Give up
            print(f"Failed to parse JSON: {candidate[:300]}" )
            return []
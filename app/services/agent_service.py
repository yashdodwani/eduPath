import os
import json
import datetime
import re
from dotenv import load_dotenv
import google.generativeai as genai
from typing import Optional, List
from app.models.schemas import UserProfile, RoadmapResponse, AgentLog as AgentLogSchema
from app.utils.prompts import MARKET_ANALYST_PROMPT, ARCHITECT_PROMPT, CURATOR_PROMPT, CRITIC_PROMPT

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
if API_KEY:
    # trim whitespace and surrounding quotes if present
    API_KEY = API_KEY.strip().strip('"').strip("'")

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not set in the environment. Set it in your .env or environment variables.")

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# Add DB imports lazily to avoid import cycles during test runs
try:
    from app.db import models as db_models
    from sqlalchemy.orm import Session
except Exception:
    db_models = None
    Session = None

class AgentWorkflow:
    def __init__(self, db_session: Optional[Session] = None):
        self.logs = []
        self.db = db_session
        self._current_roadmap_id: Optional[int] = None

    def _call_model(self, prompt: str):
        """Centralized Gemini call wrapper. Returns the raw response object.
        Raises RuntimeError with a clear message when the API request fails (e.g. invalid API key).
        """
        try:
            resp = model.generate_content(prompt)
            return resp
        except Exception as e:
            # Avoid returning raw exception objects to clients; raise a RuntimeError with a concise message
            msg = str(e)
            # Provide a helpful hint if it looks like an auth problem
            if "API key" in msg or "API_KEY" in msg or "invalid" in msg.lower():
                raise RuntimeError("Gemini API error: invalid or missing GEMINI_API_KEY. Rotate the key and set GEMINI_API_KEY in your .env")
            raise RuntimeError(f"Gemini API request failed: {msg}")

    def _log(self, agent: str, action: str):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.logs.append(AgentLogSchema(agent_name=agent, action=action, timestamp=timestamp))
        # Also persist log if DB session available
        if self.db and db_models and getattr(self, "_current_roadmap_id", None):
            db_log = db_models.AgentLog(roadmap_id=self._current_roadmap_id, agent_name=agent, action=action, timestamp=timestamp)
            self.db.add(db_log)
            self.db.commit()
            self.db.refresh(db_log)

    async def generate_learning_path(self, profile: UserProfile, completed_module_ids: Optional[List[int]] = None) -> RoadmapResponse:

        # Include progress context into prompts if provided
        progress_note = ""
        if completed_module_ids:
            progress_note = f"\n\nNOTE: The learner has completed modules with ids: {completed_module_ids}. When creating the updated path, skip or adapt content for those completed modules."

        # --- STEP 1: MARKET ANALYST AGENT ---
        self._log("Market Analyst", f"Scanning job boards for '{profile.target_role}'...")
        market_response = self._call_model(MARKET_ANALYST_PROMPT.format(target_role=profile.target_role))
        # Clean generic markdown json blocks or extract JSON from free text
        market_data = self._clean_json(market_response.text)
        self._log("Market Analyst", f"Identified {len(market_data)} critical skills.")

        # --- STEP 2: ARCHITECT AGENT ---
        self._log("Architect", "Designing curriculum structure based on gap analysis...")
        architect_prompt = ARCHITECT_PROMPT.format(
            current_skills=profile.current_skills,
            target_role=profile.target_role,
            market_trends=json.dumps(market_data)
        ) + progress_note
        architect_response = self._call_model(architect_prompt)
        structure_data = self._clean_json(architect_response.text)
        self._log("Architect", f"Created {len(structure_data)} modules.")

        # --- STEP 3: CURATOR AGENT ---
        self._log("Curator", f"Sourcing {profile.preferred_style} resources for modules...")
        curator_prompt = CURATOR_PROMPT.format(
            preferred_style=profile.preferred_style,
            modules=json.dumps(structure_data)
        )
        curator_prompt = curator_prompt + progress_note
        curator_response = self._call_model(curator_prompt)
        curated_data = self._clean_json(curator_response.text)

        # --- STEP 4: CRITIC AGENT ---
        self._log("Critic", "Validating logical flow and prerequisites...")
        critic_prompt = CRITIC_PROMPT.format(curated_path=json.dumps(curated_data)) + progress_note
        critic_response = self._call_model(critic_prompt)
        final_roadmap = self._clean_json(critic_response.text)
        self._log("System", "Roadmap generation complete.")

        # Normalize the final roadmap to match Pydantic schemas
        normalized_roadmap = self._normalize_roadmap(final_roadmap)

        # Save to DB if session present
        saved_ids = None
        if self.db and db_models:
            saved_ids = self._save_roadmap_to_db(profile, market_data, normalized_roadmap)
            # attach roadmap_id to logs for proper linkage
            self._current_roadmap_id = saved_ids.get("roadmap_id")

        return RoadmapResponse(
            market_analysis=market_data,
            roadmap=normalized_roadmap,
            agent_logs=self.logs
        )

    def generate_learning_path_sync(self, profile: UserProfile, completed_module_ids: Optional[List[int]] = None) -> dict:
        """Synchronous wrapper used by synchronous endpoints to generate and save a roadmap.
        Returns a dict with saved ids.
        """
        # Call the same logic synchronously by running the async function
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(self.generate_learning_path(profile, completed_module_ids=completed_module_ids))
        # after generation, return saved roadmap id if available
        roadmap_id = getattr(self, "_current_roadmap_id", None)
        # create a conversation id equal to roadmap_id for simplicity
        return {"roadmap_id": roadmap_id, "conversation_id": roadmap_id}

    def _save_roadmap_to_db(self, profile: UserProfile, market_analysis, roadmap):
        """Persist roadmap, modules, resources, and agent logs to the database."""
        if not self.db or not db_models:
            return {}
        # Create or fetch user (simple behavior: create new user record per request)
        user = db_models.User(name=profile.name)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)

        roadmap_row = db_models.Roadmap(
            user_id=user.id,
            target_role=profile.target_role,
            market_analysis=json.dumps(market_analysis),
            profile=json.dumps(profile.dict())
        )
        self.db.add(roadmap_row)
        self.db.commit()
        self.db.refresh(roadmap_row)

        # Save modules and resources
        for m in roadmap:
            module_row = db_models.Module(
                roadmap_id=roadmap_row.id,
                module_index=m.get("id", 0),
                module_name=m.get("module_name", ""),
                description=m.get("description", ""),
                skills_covered=json.dumps(m.get("skills_covered", [])),
                why_needed=m.get("why_needed", ""),
                estimated_time=m.get("estimated_time", "")
            )
            self.db.add(module_row)
            self.db.commit()
            self.db.refresh(module_row)

            for r in m.get("resources", []):
                resource_row = db_models.Resource(
                    module_id=module_row.id,
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    type=r.get("type", "Article"),
                    duration=r.get("duration", ""),
                    reason=r.get("reason", "")
                )
                self.db.add(resource_row)
            self.db.commit()

        # Save agent logs
        for log in self.logs:
            log_row = db_models.AgentLog(
                roadmap_id=roadmap_row.id,
                agent_name=log.agent_name,
                action=log.action,
                timestamp=log.timestamp
            )
            self.db.add(log_row)
        self.db.commit()

        # store current roadmap id for other operations
        self._current_roadmap_id = roadmap_row.id
        return {"roadmap_id": roadmap_row.id}

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


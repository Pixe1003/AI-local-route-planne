from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class AgentSkill:
    name: str
    path: Path
    content: str


class AgentSkillRegistry:
    AGENT_SKILL_PATHS = {
        "local_route": "local-route-agent/SKILL.md",
        "need_profile": "need-profile-agent/SKILL.md",
        "recommend": "recommend-agent/SKILL.md",
        "route_planning": "route-planning-agent/SKILL.md",
        "replan": "replan-agent/SKILL.md",
        "trip_manager": "trip-manager-agent/SKILL.md",
    }

    def __init__(self, skills_root: Path | None = None) -> None:
        self.skills_root = skills_root or self._default_skills_root()
        self._cache: dict[str, AgentSkill | None] = {}

    def get_skill(self, agent_name: str) -> AgentSkill | None:
        normalized = self._normalize_agent_name(agent_name)
        if normalized not in self._cache:
            self._cache[normalized] = self._load_skill(normalized)
        return self._cache[normalized]

    def build_system_prompt(self, agent_name: str | None, base_prompt: str) -> str:
        if not agent_name:
            return base_prompt
        skill = self.get_skill(agent_name)
        if skill is None:
            return base_prompt
        return (
            f"{base_prompt}\n\n"
            f"<agent_skill name=\"{skill.name}\">\n"
            f"{skill.content.strip()}\n"
            f"</agent_skill>"
        )

    def _load_skill(self, agent_name: str) -> AgentSkill | None:
        relative_path = self.AGENT_SKILL_PATHS.get(agent_name)
        if relative_path is None:
            return None
        path = self.skills_root / relative_path
        if not path.exists():
            return None
        return AgentSkill(
            name=agent_name,
            path=path,
            content=path.read_text(encoding="utf-8"),
        )

    def _normalize_agent_name(self, agent_name: str) -> str:
        return agent_name.strip().lower().replace("-", "_")

    def _default_skills_root(self) -> Path:
        project_root = Path(__file__).resolve().parents[3]
        return project_root / "skills"


@lru_cache
def get_agent_skill_registry() -> AgentSkillRegistry:
    return AgentSkillRegistry()


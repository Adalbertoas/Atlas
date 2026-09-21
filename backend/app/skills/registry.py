from __future__ import annotations

from app.skills.base import Skill


class SkillRegistry:
    """Registro de Skills, equivalente al ToolRegistry pero independiente."""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        if skill.id in self._skills:
            raise ValueError(f"La skill '{skill.id}' ya está registrada.")
        self._skills[skill.id] = skill

    def unregister(self, skill_id: str) -> Skill | None:
        return self._skills.pop(skill_id, None)

    def get(self, skill_id: str) -> Skill | None:
        return self._skills.get(skill_id)

    def list(self) -> list[Skill]:
        return list(self._skills.values())

    def find_by_tag(self, tag: str) -> list[Skill]:
        needle = tag.lower()
        return [skill for skill in self._skills.values() if needle in {t.lower() for t in skill.definition.tags}]

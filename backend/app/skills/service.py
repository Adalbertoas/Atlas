from app.skills.registry import SkillRegistry
from app.skills.memory import MemorySkill
from app.skills.smart_home import SmartHomeSkill
from app.skills.system import SystemSkill


def build_default_registry() -> SkillRegistry:
    registry = SkillRegistry()
    for skill in (SystemSkill(), MemorySkill(), SmartHomeSkill()):
        registry.register(skill)
    return registry


skill_registry = build_default_registry()

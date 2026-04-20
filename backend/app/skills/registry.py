from pathlib import Path

import frontmatter
from pydantic import BaseModel

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = BACKEND_ROOT / "skills"


class SkillMeta(BaseModel):
    name: str
    description: str
    when_to_use: str


class Skill(SkillMeta):
    content: str


def _load_all() -> dict[str, Skill]:
    skills: dict[str, Skill] = {}
    if not SKILLS_DIR.exists():
        return skills
    for md in sorted(SKILLS_DIR.glob("*.md")):
        if md.name.lower() == "readme.md":
            continue
        post = frontmatter.load(md)
        skill = Skill.model_validate({**post.metadata, "content": post.content})
        if skill.name in skills:
            raise ValueError(f"Duplicate skill name '{skill.name}' in {md}")
        skills[skill.name] = skill
    return skills


SKILLS: dict[str, Skill] = _load_all()


def catalog_prompt() -> str:
    """给 system prompt 用：列出每个 skill 的 name + when_to_use。"""
    return "\n".join(f"- `{s.name}`: {s.when_to_use}" for s in SKILLS.values())


def load_skill_content(name: str) -> str:
    """给 load_skill tool 用：返回 skill 的完整 markdown body。
    找不到时返回友好错误字符串而不是抛异常——让模型能自纠错。
    """
    skill = SKILLS.get(name)
    if skill is None:
        available = ", ".join(SKILLS.keys()) or "(none)"
        return f"Skill '{name}' not found. Available skills: {available}"
    return skill.content

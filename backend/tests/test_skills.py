from app.skills.registry import SKILLS, catalog_prompt, load_skill_content


def test_at_least_one_skill_loaded():
    assert len(SKILLS) >= 1
    assert "margin-of-safety" in SKILLS


def test_loaded_skill_has_metadata_and_content():
    skill = SKILLS["margin-of-safety"]
    assert skill.name == "margin-of-safety"
    assert skill.description
    assert skill.when_to_use
    assert skill.content.strip()


def test_catalog_prompt_mentions_known_skill():
    catalog = catalog_prompt()
    assert "margin-of-safety" in catalog
    assert catalog.startswith("-")


def test_load_skill_content_returns_body_for_known_name():
    body = load_skill_content("margin-of-safety")
    assert "Margin of Safety" in body
    assert "---" not in body[:10]


def test_load_skill_content_returns_friendly_error_for_unknown_name():
    msg = load_skill_content("does-not-exist")
    assert "not found" in msg.lower()
    assert "margin-of-safety" in msg

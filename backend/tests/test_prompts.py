from app.agent.prompts import KICKOFF_MESSAGE, build_system_prompt


def test_prompt_includes_learner_context() -> None:
    prompt = build_system_prompt(
        {
            "profile": {
                "name": "Anna",
                "level": "B1",
                "main_topic": "Job interviews",
                "goal": "",
                "preferences": {"correction_style": "only major mistakes"},
            },
            "topic": "Salary negotiation",
            "previous_summaries": [
                {
                    "date": "2026-10-01",
                    "topic": "Job interviews",
                    "summary": "Practiced self-introduction.",
                    "recurring_mistakes": ["present perfect"],
                    "next_steps": ["practice salary questions"],
                }
            ],
        }
    )
    assert "Name: Anna" in prompt
    assert "Topic: Salary negotiation" in prompt
    assert "correction_style: only major mistakes" in prompt
    assert "Practiced self-introduction." in prompt
    assert KICKOFF_MESSAGE in prompt


def test_prompt_for_first_lesson() -> None:
    prompt = build_system_prompt({"profile": {"name": "Anna"}, "topic": "Small talk"})
    assert "This is the learner's first lesson." in prompt
    assert "No previous lessons yet." in prompt

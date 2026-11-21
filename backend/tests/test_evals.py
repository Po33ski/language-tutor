"""The eval harness itself, with a fake model: no paid calls."""

import asyncio
from collections import Counter
from dataclasses import replace

import pytest
from langchain_core.messages import AIMessage

from evals.cases import CASES
from evals.checks import format_failures, tool_failures
from evals.harness import run_case
from evals.run import grade_programmatic, wilson_interval
from evals.schema import Case, CaseRun, ToolCall, Turn
from tests.conftest import FakeTutorModel, mistake_call

GOOD_REPLY = 'Small fix: we say "I am 30." What do you do at the bank?'
CASE = Case(
    id="example",
    tag="mistakes",
    turns=("I have 30 years.",),
    criteria=("Mentions the fix.",),
    mistakes_min=1,
    mistakes_max=2,
    corrected_any=(("am 30",),),
    forbidden_tools=("save_preference",),
)


def _run(reply: str, *calls: ToolCall, time_up: bool = False) -> CaseRun:
    turn = Turn(learner="I have 30 years.", reply=reply, tool_calls=calls)
    return CaseRun(turns=[turn], system_prompt="", time_up=time_up)


MISTAKE = ToolCall(
    "record_mistake",
    {"original": "I have 30 years", "corrected": "I am 30", "explanation": "Age uses 'be'."},
)


def test_cases_are_well_formed() -> None:
    ids = [case.id for case in CASES]
    assert len(ids) == len(set(ids))
    assert all(case.turns and case.criteria for case in CASES)
    tags = Counter(case.tag for case in CASES)
    assert set(tags) == {"mistakes", "no_mistakes", "intent", "adherence", "clock"}
    # Both directions: errors to catch, and correct English to leave alone.
    assert tags["no_mistakes"] >= 5


def test_oracle_passes_and_null_fails() -> None:
    assert grade_programmatic(CASE, _run(GOOD_REPLY, MISTAKE))[:2] == (True, True)
    assert grade_programmatic(CASE, _run(""))[:2] == (False, False)


@pytest.mark.parametrize(
    "reply",
    [
        "One. " * 11,
        "First question? Second question? Third question?",
        "**Bold** text.",
        "- a list item",
        "Great job! 🎉",
    ],
)
def test_format_rules_catch_violations(reply: str) -> None:
    assert format_failures(reply)


def test_quoted_corrections_do_not_count_as_sentences() -> None:
    assert not format_failures('We say "I am 30. I work here." Nice. Tell me more. Why?')


def test_a_quote_can_end_a_sentence() -> None:
    reply = 'We say "I am 30." ' * 11
    assert format_failures(reply) == ["11 sentences (max 10)"]


def test_two_questions_are_allowed() -> None:
    assert not format_failures("Nice. What is your job? Why do you like it?")
    assert not format_failures("What is your job, and why do you like it?")


def test_closing_message_has_no_question() -> None:
    assert format_failures("Thanks, goodbye! See you?", closing=True)
    assert not format_failures("Thanks for today, Sam. Goodbye!", closing=True)


@pytest.mark.parametrize(
    "args",
    [
        {"original": "not what they said", "corrected": "I am 30"},
        {"original": "I have 30 years", "corrected": "I am 30 / I'm 30"},
        {"original": "I have 30 years", "corrected": "something else"},
    ],
)
def test_tool_checks_catch_bad_corrections(args: dict) -> None:
    assert tool_failures(CASE, _run(GOOD_REPLY, ToolCall("record_mistake", args)))


def test_tool_checks_catch_duplicates_and_forbidden_tools() -> None:
    assert tool_failures(CASE, _run(GOOD_REPLY, MISTAKE, MISTAKE))
    preference = ToolCall("save_preference", {"key": "a", "value": "b"})
    assert tool_failures(CASE, _run(GOOD_REPLY, MISTAKE, preference))


@pytest.mark.parametrize(
    "reply",
    [
        'We say "at the meeting" or "in the meeting". What happened?',
        "We say “at the meeting” or “in the meeting”.",
        "We say 'I am 30' or 'I'm 30 years old'.",
        'We say "I am 30" / "I\'m 30".',
    ],
)
def test_tool_checks_catch_alternatives_in_the_reply(reply: str) -> None:
    assert "the reply offers alternative corrections" in tool_failures(CASE, _run(reply, MISTAKE))


def test_a_case_can_allow_two_common_wordings() -> None:
    reply = 'We say "I am 30 years old" or "I\'m 30."'
    assert tool_failures(CASE, _run(reply, MISTAKE))
    assert not tool_failures(replace(CASE, allow_variants=True), _run(reply, MISTAKE))


def test_alternatives_rule_leaves_other_replies_alone() -> None:
    single = 'We say "I am 30", not "I have 30 years". Do you like it or not?'
    assert not tool_failures(CASE, _run(single, MISTAKE))
    # Offering a choice of words is fine when nothing is being corrected.
    vocabulary = replace(CASE, mistakes_min=0, corrected_any=())
    choice = 'You could say "collaborative" or "a team player".'
    assert not tool_failures(vocabulary, _run(choice))


def test_wilson_interval_contains_the_rate() -> None:
    low, high = wilson_interval(8, 10)
    assert low < 0.8 < high
    assert wilson_interval(0, 0) == (0.0, 0.0)


def test_harness_runs_the_real_lesson_code() -> None:
    model = FakeTutorModel(
        messages=iter(
            [
                AIMessage("Hi Sam!"),
                mistake_call("I have 30 years", "I am 30", "Age uses 'be'."),
                AIMessage(GOOD_REPLY),
            ]
        )
    )
    run = asyncio.run(run_case(CASE, model))
    assert run.graded.reply == GOOD_REPLY
    assert [call.name for call in run.graded.tool_calls] == ["record_mistake"]
    assert "Name: Sam" in run.system_prompt
    assert grade_programmatic(CASE, run)[:2] == (True, True)


def test_harness_moves_the_lesson_clock() -> None:
    case = Case(
        id="late",
        tag="clock",
        turns=("Thanks.",),
        criteria=("Says goodbye.",),
        elapsed_minutes=16,
        expect_time_up=True,
    )
    model = FakeTutorModel(messages=iter([AIMessage("Hi!"), AIMessage("Thank you. Goodbye!")]))
    run = asyncio.run(run_case(case, model))
    assert run.time_up is True
    assert model.inputs[-1][-1].content.startswith("[Lesson clock: time is up")

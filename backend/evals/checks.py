"""Checks that need no model: reply format and tool use. Free and deterministic."""

import re

from evals.schema import Case, CaseRun

MAX_SENTENCES = 10
# Asking about two things at once is fine; more is too much for one spoken reply.
MAX_QUESTIONS = 2

# Quoted text is usually a correction ("we say 'I am 30.'"), not a sentence of the reply.
_QUOTED = re.compile(r"\"[^\"]*\"|“[^”]*”|(?<!\w)'[^'\n]*'(?!\w)|‘[^’]*’")
_ABBREVIATIONS = re.compile(r"\b(?:e\.g\.|i\.e\.|Mr\.|Mrs\.|Ms\.|Dr\.|etc\.)", re.IGNORECASE)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
_MARKDOWN = re.compile(r"\*\*|`|^#{1,6}\s|^\s*[-*]\s|^\s*\d+\.\s", re.MULTILINE)
_EMOJI = re.compile("[\U0001f300-\U0001faff☀-➿]")
# Two quoted wordings offered as a choice: "at the meeting" or "in the meeting".
_ALTERNATIVES = re.compile(
    r"(?:\"[^\"\n]+\"|“[^”\n]+”|(?<!\w)'[^'\n]+'(?!\w)|‘[^’\n]+’)"
    r"[,.]?\s+(?:or|/)\s+(?:\"|“|‘|(?<!\w)')",
    re.IGNORECASE,
)


def normalize(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'")
    return " ".join(text.lower().split()).strip(" .,!?;:\"'")


def _without_quotes(reply: str) -> str:
    # A quote that ends with . ! or ? can also end the tutor's sentence.
    def placeholder(match: re.Match[str]) -> str:
        return "X." if match.group(0)[-2:-1] in (".", "!", "?") else "X"

    return _ABBREVIATIONS.sub("x", _QUOTED.sub(placeholder, reply))


def format_failures(reply: str, *, closing: bool = False) -> list[str]:
    """The reply rules from the tutor's prompt: it is read aloud."""
    if not reply.strip():
        return ["the reply is empty"]
    failures = []
    plain = _without_quotes(reply).strip()
    sentences = len(_SENTENCE_END.split(plain))
    if sentences > MAX_SENTENCES:
        failures.append(f"{sentences} sentences (max {MAX_SENTENCES})")
    questions = plain.count("?")
    if closing and questions:
        failures.append("the closing message asks a question")
    elif questions > MAX_QUESTIONS:
        failures.append(f"{questions} questions (max {MAX_QUESTIONS})")
    if _MARKDOWN.search(reply):
        failures.append("contains markdown")
    if _EMOJI.search(reply):
        failures.append("contains emoji")
    return failures


def tool_failures(case: Case, run: CaseRun) -> list[str]:
    """Whether the graded turn used the right tools with the right arguments."""
    turn = run.graded
    failures = []
    names = [call.name for call in turn.tool_calls]
    mistakes = [call.args for call in turn.tool_calls if call.name == "record_mistake"]

    if len(mistakes) < case.mistakes_min:
        failures.append(f"recorded {len(mistakes)} mistake(s), expected >= {case.mistakes_min}")
    if case.mistakes_max is not None and len(mistakes) > case.mistakes_max:
        failures.append(f"recorded {len(mistakes)} mistake(s), expected <= {case.mistakes_max}")

    learner = normalize(turn.learner)
    originals = [normalize(str(m.get("original", ""))) for m in mistakes]
    for original in originals:
        if not original or original not in learner:
            failures.append(f"'original' is not the learner's wording: {original!r}")
    if len(set(originals)) < len(originals):
        failures.append("the same mistake was recorded twice")

    corrections = [normalize(str(m.get("corrected", ""))) for m in mistakes]
    for correction in corrections:
        if " / " in correction:
            failures.append(f"correction offers alternatives: {correction!r}")
    if mistakes and not case.allow_variants and _ALTERNATIVES.search(turn.reply):
        failures.append("the reply offers alternative corrections")
    for accepted in case.corrected_any:
        if not any(normalize(option) in text for option in accepted for text in corrections):
            failures.append(f"no correction contains any of {list(accepted)}")

    for tool in case.required_tools:
        if tool not in names:
            failures.append(f"did not call {tool}")
    for tool in case.forbidden_tools:
        if tool in names:
            failures.append(f"should not call {tool}")
    return failures


def clock_failures(case: Case, run: CaseRun) -> list[str]:
    if run.time_up != case.expect_time_up:
        return [f"time_up was {run.time_up}, expected {case.expect_time_up}"]
    return []

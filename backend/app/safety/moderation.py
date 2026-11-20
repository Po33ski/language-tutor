"""Moderation: every learner message is checked before it reaches the tutor.

A local toxicity classifier from Hugging Face (`unitary/unbiased-toxic-roberta`, the
"unbiased" Detoxify model) scores the message; `decide` turns the scores into a verdict.
It runs on the CPU in about 50 ms, so it adds almost no delay, costs nothing and the
message never leaves the server for this check. It is trained on English text.

The policy is tuned for a language course, where learners ask about rude words, vent
about hard exercises and make mistakes:
- Blocked: threats, attacks on a group (hate), sexual messages, and insults aimed at
  someone ("you idiot", "you are a stupid bot").
- Let through (the tutor answers calmly, see the prompt): swearing out of frustration
  ("this is so damn hard"), insults that are not aimed at anyone ("this exercise is
  stupid"), and words quoted to ask about them ("what does 'damn' mean?").

The thresholds were picked on a set of typical learner messages; see README → Moderation.
"""

import asyncio
import logging
import re
import threading
from collections.abc import Mapping
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ModerationCategory(StrEnum):
    THREAT = "threat"
    INSULT = "insult"
    HATE = "hate"
    SEXUAL = "sexual"


class ModerationVerdict(BaseModel):
    allowed: bool
    # Why the message was blocked; None when it is allowed.
    category: ModerationCategory | None = None
    # The classifier's scores (0-1 per label), for logs and tests.
    scores: dict[str, float] = {}


ALLOWED = ModerationVerdict(allowed=True)

# Shown to the learner when a message is blocked (in the app's voice, no apology).
BLOCKED_MESSAGES: dict[ModerationCategory, str] = {
    ModerationCategory.THREAT: (
        "This message wasn't sent because it reads as a threat. "
        "Rephrase it and keep the conversation friendly."
    ),
    ModerationCategory.INSULT: (
        "This message wasn't sent because it insults someone. "
        "Rephrase it and keep the conversation respectful."
    ),
    ModerationCategory.HATE: (
        "This message wasn't sent because it attacks a group of people. "
        "Rephrase it and keep the conversation respectful."
    ),
    ModerationCategory.SEXUAL: (
        "This message wasn't sent because it contains sexual content. "
        "Keep the conversation on the lesson topic."
    ),
}

# Score thresholds per classifier label. Threats sit at 0.72-0.98 in the sample set,
# idioms like "I could kill for a coffee" at 0.65-0.67.
THREAT_THRESHOLD = 0.7
HATE_THRESHOLD = 0.5  # label "identity_attack"
SEVERE_THRESHOLD = 0.5  # label "severe_toxicity", counted as an insult
# Sexual messages scored 0.21-0.88, ordinary ones (dating, sex education) about 0.00.
SEXUAL_THRESHOLD = 0.2
# The "insult" score is high for any insulting word, also in "this exercise is stupid",
# so an insult is blocked only when it is also aimed at the reader (see `is_addressed`).
INSULT_THRESHOLD = 0.9
POLICY_LABELS = (
    "toxicity",
    "severe_toxicity",
    "obscene",
    "insult",
    "threat",
    "identity_attack",
    "sexual_explicit",
)

# Quoted words are mentioned, not used: "how do you say 'idiot' politely?". The quote must
# not touch a letter on its outer side, so apostrophes ("I'm", "don't") are not quotes.
_QUOTED = re.compile(
    r"(?<![\w])(?:'[^'\n]{1,80}'|‘[^’\n]{1,80}’|\"[^\"\n]{1,80}\"|“[^”\n]{1,80}”)(?![\w])"
)
# Second-person address: "you are / you're / ur / are you", "..., you idiot", or a
# message that starts with "you".
_ADDRESSED = re.compile(
    r"\b(?:you|u)\s*(?:are|r|'re|’re)\b|\byou'?re\b|\bur\b|\bare\s+(?:you|u)\b"
    r"|,\s*(?:you|u)\b|^\W*(?:you|u)\b|\b(?:fuck|screw)\s+(?:you|u)\b",
    re.IGNORECASE,
)

# The classifier reads at most 512 tokens; longer messages are scored in chunks.
_CHUNK_CHARS = 1000


def strip_quoted(text: str) -> str:
    """The message without quoted words or phrases."""
    return _QUOTED.sub(" ", text)


def is_addressed(text: str) -> bool:
    """Whether the message speaks to someone directly ("you are...", "..., you idiot")."""
    return bool(_ADDRESSED.search(text))


def decide(text: str, scores: Mapping[str, float]) -> ModerationVerdict:
    """The verdict for a message (already without quoted words) and its scores."""

    def score(label: str) -> float:
        return scores.get(label, 0.0)

    # The first matching rule names the category (and so the message the learner sees);
    # insults come before sexual content, because abuse like "f*** you" scores on both.
    category = None
    if score("threat") >= THREAT_THRESHOLD:
        category = ModerationCategory.THREAT
    elif score("identity_attack") >= HATE_THRESHOLD:
        category = ModerationCategory.HATE
    elif score("severe_toxicity") >= SEVERE_THRESHOLD or (
        score("insult") >= INSULT_THRESHOLD and is_addressed(text)
    ):
        category = ModerationCategory.INSULT
    elif score("sexual_explicit") >= SEXUAL_THRESHOLD:
        category = ModerationCategory.SEXUAL
    # The model also scores identity mentions ("male", "muslim", ...); they are not
    # verdicts, so only the labels above are kept (and logged).
    kept = {label: scores[label] for label in POLICY_LABELS if label in scores}
    return ModerationVerdict(allowed=category is None, category=category, scores=kept)


class Moderator(Protocol):
    async def check(self, text: str) -> ModerationVerdict: ...

    async def warm_up(self) -> None: ...


class LocalModerator:
    """The Hugging Face classifier in this process, loaded on first use (on the CPU)."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._pipeline = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._pipeline is None:
                # Imported here, so tests and the app's startup do not pay for it.
                from transformers import pipeline

                self._pipeline = pipeline(
                    "text-classification",
                    model=self._model_name,
                    top_k=None,  # every label, not just the top one
                    function_to_apply="sigmoid",  # labels are independent (multi-label)
                    device="cpu",
                )
            return self._pipeline

    def _scores(self, text: str) -> dict[str, float]:
        """Highest score per label over the message's chunks."""
        chunks = [text[i : i + _CHUNK_CHARS] for i in range(0, len(text), _CHUNK_CHARS)]
        scores: dict[str, float] = {}
        for result in self._load()(chunks, truncation=True):
            for item in result:
                scores[item["label"]] = max(scores.get(item["label"], 0.0), item["score"])
        return scores

    async def check(self, text: str) -> ModerationVerdict:
        used = strip_quoted(text)
        if not used.strip():
            return ALLOWED
        try:
            scores = await asyncio.to_thread(self._scores, used)
        except Exception:
            # A broken check must not stop the lesson: let the message through, loudly.
            logger.exception("Moderation check failed; the message was let through")
            return ALLOWED
        return decide(used, scores)

    async def warm_up(self) -> None:
        await asyncio.to_thread(self._load)

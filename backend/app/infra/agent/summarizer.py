"""Turns a finished lesson into long-term memory: a lesson summary and a progress profile."""

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import Settings
from app.domain.learners.models import Profile
from app.domain.lessons.models import LessonSummary, Mistake, VocabularyItem

SUMMARY_SYSTEM_PROMPT = """\
You summarize English lessons for a tutoring app. The summary is stored in the \
learner's long-term memory and shown to the tutor before future lessons, and to the \
learner as feedback.

Be concrete and specific to this lesson: name the actual situations practiced, the \
actual grammar or word-choice problems, and the actual words introduced. Write in \
simple English the learner (level {level}) can understand. Address the learner as \
"you". Keep every list item short (one line). Do not invent anything that is not in \
the transcript."""

SUMMARY_USER_PROMPT = """\
Lesson topic: {topic}

Mistakes recorded by the tutor during the lesson:
{mistakes}

Vocabulary introduced by the tutor:
{vocabulary}

Transcript:
{transcript}"""

PROGRESS_SYSTEM_PROMPT = """\
You maintain a short progress profile of an English learner. The tutor reads it before \
every lesson to adapt teaching.

Update the existing profile with what the latest lesson showed. Keep information that \
is still true, revise what changed (e.g. a problem the learner has now overcome) and \
add new observations. Cover: estimated current level, strengths, persistent problems \
and what to focus on next. Write at most 120 words of plain text, no markdown. Reply \
with the updated profile only."""

PROGRESS_USER_PROMPT = """\
Learner: {name}, self-assessed level {level}, main topic: {main_topic}.

Current progress profile:
{previous}

Latest lesson ({date}, topic: {topic}):
{summary}
Practiced: {practiced}
Recurring mistakes: {mistakes}
Next steps: {next_steps}"""


def _bullets(lines: list[str]) -> str:
    return "\n".join(f"- {line}" for line in lines) if lines else "- none"


class LlmSummarizer:
    """Summarizer backed by a chat model (Claude Haiku by default)."""

    def __init__(self, model: BaseChatModel) -> None:
        self._model = model
        # Native structured output: works with adaptive thinking, unlike forced tool use.
        self._structured = model.with_structured_output(LessonSummary, method="json_schema")

    async def summarize(
        self,
        *,
        profile: Profile,
        topic: str,
        transcript: str,
        mistakes: list[Mistake],
        vocabulary: list[VocabularyItem],
    ) -> LessonSummary:
        user_prompt = SUMMARY_USER_PROMPT.format(
            topic=topic,
            mistakes=_bullets(
                [f"{m['original']} -> {m['corrected']} ({m['explanation']})" for m in mistakes]
            ),
            vocabulary=_bullets([f"{v['word']}: {v['meaning']}" for v in vocabulary]),
            transcript=transcript,
        )
        return await self._structured.ainvoke(
            [
                SystemMessage(SUMMARY_SYSTEM_PROMPT.format(level=profile.level)),
                HumanMessage(user_prompt),
            ]
        )

    async def update_progress(
        self, *, profile: Profile, previous: str, date: str, topic: str, summary: LessonSummary
    ) -> str:
        user_prompt = PROGRESS_USER_PROMPT.format(
            name=profile.name,
            level=profile.level,
            main_topic=profile.main_topic,
            previous=previous or "(empty - this was the first lesson)",
            date=date,
            topic=topic,
            summary=summary.summary,
            practiced="; ".join(summary.practiced) or "none",
            mistakes="; ".join(summary.recurring_mistakes) or "none",
            next_steps="; ".join(summary.next_steps) or "none",
        )
        response = await self._model.ainvoke(
            [SystemMessage(PROGRESS_SYSTEM_PROMPT), HumanMessage(user_prompt)]
        )
        return response.text.strip()


def build_summarizer(settings: Settings) -> LlmSummarizer:
    model = init_chat_model(
        settings.llm_model,
        api_key=settings.anthropic_api_key,
        max_tokens=4096,
        output_config={"effort": settings.summary_effort},
    )
    return LlmSummarizer(model)

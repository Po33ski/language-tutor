import operator
from typing import Annotated, NotRequired

from langchain.agents import AgentState

from app.domain.lessons.models import Mistake, VocabularyItem


class TutorState(AgentState):
    """Short-term memory of one lesson (one LangGraph thread).

    Learner context is copied in at lesson start, so the system prompt stays the same
    for the whole lesson.
    """

    user_id: NotRequired[str]
    profile: NotRequired[dict]
    topic: NotRequired[str]
    # Planned length; missing for lessons created before lessons had a length.
    lesson_minutes: NotRequired[int]
    progress: NotRequired[str]
    previous_summaries: NotRequired[list[dict]]
    mistakes: NotRequired[Annotated[list[Mistake], operator.add]]
    vocabulary: NotRequired[Annotated[list[VocabularyItem], operator.add]]

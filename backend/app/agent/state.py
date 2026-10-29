import operator
from typing import Annotated, NotRequired, TypedDict

from langchain.agents import AgentState


class Mistake(TypedDict):
    original: str
    corrected: str
    explanation: str


class VocabularyItem(TypedDict):
    word: str
    meaning: str
    example: str


class TutorState(AgentState):
    """Short-term memory of one lesson (one LangGraph thread).

    Learner context is copied in at lesson start, so the system prompt stays the same
    for the whole lesson.
    """

    user_id: NotRequired[str]
    profile: NotRequired[dict]
    topic: NotRequired[str]
    progress: NotRequired[str]
    previous_summaries: NotRequired[list[dict]]
    mistakes: NotRequired[Annotated[list[Mistake], operator.add]]
    vocabulary: NotRequired[Annotated[list[VocabularyItem], operator.add]]

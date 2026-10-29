"""Helpers for reading a lesson's conversation out of its LangGraph thread."""

from collections.abc import Sequence
from typing import Literal

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from pydantic import BaseModel

# Id prefix of the hidden message that starts a lesson.
KICKOFF_ID_PREFIX = "kickoff-"


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


def thread_config(lesson_id: str) -> dict:
    return {"configurable": {"thread_id": lesson_id}}


def to_chat_messages(messages: Sequence[AnyMessage]) -> list[ChatMessage]:
    """Visible conversation only: no kickoff signal, tool calls or tool results.

    Consecutive assistant texts (e.g. before and after a tool call) are merged into one
    message, matching how they were streamed.
    """
    result: list[ChatMessage] = []
    for message in messages:
        if isinstance(message, HumanMessage):
            if not (message.id or "").startswith(KICKOFF_ID_PREFIX):
                result.append(ChatMessage(role="user", content=message.text))
        elif isinstance(message, AIMessage) and message.text.strip():
            if result and result[-1].role == "assistant":
                result[-1].content += message.text
            else:
                result.append(ChatMessage(role="assistant", content=message.text))
    return result


def format_transcript(messages: Sequence[ChatMessage]) -> str:
    speakers = {"user": "Learner", "assistant": "Tutor"}
    return "\n\n".join(f"{speakers[m.role]}: {m.content}" for m in messages)

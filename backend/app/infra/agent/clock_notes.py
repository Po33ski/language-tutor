"""Shows the model the lesson clock note stored with each learner message."""

from collections.abc import Sequence

from langchain_core.messages import AnyMessage, HumanMessage

# Key in a learner message's `additional_kwargs` that holds its clock note.
CLOCK_NOTE_KEY = "lesson_clock"


def with_clock_notes(messages: Sequence[AnyMessage]) -> list[AnyMessage]:
    """Copies of the messages for the model, with each clock note in front of its message."""
    result: list[AnyMessage] = []
    for message in messages:
        note = (
            message.additional_kwargs.get(CLOCK_NOTE_KEY)
            if isinstance(message, HumanMessage)
            else None
        )
        if note and isinstance(message.content, str):
            other_kwargs = {
                key: value
                for key, value in message.additional_kwargs.items()
                if key != CLOCK_NOTE_KEY
            }
            message = message.model_copy(
                update={
                    "content": f"{note}\n\n{message.content}",
                    "additional_kwargs": other_kwargs,
                }
            )
        result.append(message)
    return result
